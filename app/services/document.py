"""Document ingestion and knowledge-base processing pipeline."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import NotFoundError, ProcessingError, ValidationError
from app.core.logging import get_logger
from app.models.document import Document, DocumentChunk
from app.models.enums import DocumentStatus, DocumentType
from app.providers.chunking.base import Chunker
from app.providers.embedding.base import EmbeddingProvider
from app.providers.llm.base import LLMProvider
from app.providers.pdf.base import PDFExtractor
from app.repositories.document import DocumentChunkRepository, DocumentRepository
from app.repositories.exam import ExamRepository
from app.repositories.knowledge import KnowledgeConceptRepository
from app.schemas.document import DocumentUploadMeta
from app.utils.storage import LocalFileStorage

logger = get_logger(__name__)


class DocumentService:
    """
    Orchestrates upload + asynchronous knowledge-base generation.

    This service is the reusable business boundary for REST, MCP, CLI, and workers.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        storage: LocalFileStorage,
        pdf_extractor: PDFExtractor,
        chunker: Chunker,
        llm: LLMProvider,
        embeddings: EmbeddingProvider,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.storage = storage
        self.pdf_extractor = pdf_extractor
        self.chunker = chunker
        self.llm = llm
        self.embeddings = embeddings
        self.settings = settings or get_settings()
        self.documents = DocumentRepository(session)
        self.chunks = DocumentChunkRepository(session)
        self.exams = ExamRepository(session)
        self.concepts = KnowledgeConceptRepository(session)

    async def upload(
        self,
        *,
        meta: DocumentUploadMeta,
        filename: str,
        content_type: str,
        data: bytes,
    ) -> Document:
        if not data:
            raise ValidationError("Empty file upload")
        if len(data) > self.settings.max_upload_bytes:
            raise ValidationError(
                f"File exceeds max size of {self.settings.max_upload_size_mb} MB",
                details={"size_bytes": len(data)},
            )
        if not filename.lower().endswith(".pdf") and content_type != "application/pdf":
            raise ValidationError("Only PDF uploads are supported")

        exam = await self.exams.get_by_id(meta.exam_id)
        if not exam:
            raise NotFoundError(f"Exam {meta.exam_id} not found")

        path = self.storage.build_path(meta.exam_id, filename)
        await self.storage.save(path, data)

        document = Document(
            exam_id=meta.exam_id,
            title=meta.title,
            document_type=meta.document_type,
            status=DocumentStatus.UPLOADED,
            filename=filename,
            storage_path=str(path),
            content_type=content_type or "application/pdf",
            file_size_bytes=len(data),
            extra_metadata=meta.metadata,
        )
        document = await self.documents.create(document)
        logger.info(
            "document_uploaded",
            document_id=str(document.id),
            exam_id=str(meta.exam_id),
            type=meta.document_type.value,
        )
        return document

    async def get(self, document_id: uuid.UUID) -> Document:
        document = await self.documents.get_by_id(document_id)
        if not document:
            raise NotFoundError(f"Document {document_id} not found")
        return document

    async def list(
        self,
        *,
        exam_id: uuid.UUID | None = None,
        status: DocumentStatus | None = None,
        document_type: DocumentType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Document], int]:
        return await self.documents.list(
            exam_id=exam_id,
            status=status,
            document_type=document_type,
            limit=limit,
            offset=offset,
        )

    async def list_chunks(
        self,
        document_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[DocumentChunk], int]:
        await self.get(document_id)
        return await self.chunks.list_by_document(document_id, limit=limit, offset=offset)

    async def mark_processing(self, document_id: uuid.UUID) -> Document:
        document = await self.get(document_id)
        if document.status == DocumentStatus.PROCESSING:
            raise ValidationError(
                "Document is already processing; wait for it to finish or fail"
            )
        # Re-process allowed: process_document deletes prior chunks first
        return await self.documents.update_status(document, DocumentStatus.PROCESSING)

    async def process_document(self, document_id: uuid.UUID) -> Document:
        """
        Full knowledge-base generation pipeline for a single document.

        Intended to run outside the HTTP request lifecycle (worker / background task).
        """
        document = await self.get(document_id)
        exam = await self.exams.get_by_id(document.exam_id)
        exam_code = exam.code if exam else ""

        logger.info("document_processing_started", document_id=str(document_id))
        try:
            if document.status != DocumentStatus.PROCESSING:
                document = await self.documents.update_status(
                    document, DocumentStatus.PROCESSING
                )

            path = Path(document.storage_path)
            extracted = await self.pdf_extractor.extract(path)
            if extracted.page_count == 0 or not any(p.text.strip() for p in extracted.pages):
                raise ProcessingError("No extractable text found in PDF")

            text_chunks = self.chunker.chunk(extracted)
            if not text_chunks:
                raise ProcessingError("Chunking produced no chunks")

            logger.info(
                "document_chunked",
                document_id=str(document_id),
                pages=extracted.page_count,
                chunks=len(text_chunks),
            )

            # Replace any prior chunks (safe re-entry after partial failure)
            await self.chunks.delete_by_document(document_id)

            db_chunks: list[DocumentChunk] = []
            total = len(text_chunks)
            for tc in text_chunks:
                meta = await self.llm.extract_metadata(
                    tc.content,
                    source_type=document.document_type.value,
                    exam_code=exam_code,
                )
                embedding = await self.embeddings.generate_embedding(tc.content)
                meta_dict: dict[str, Any] = meta.model_dump()
                meta_dict["word_count"] = tc.word_count
                if tc.end_page_number is not None:
                    meta_dict["end_page_number"] = tc.end_page_number

                chunk = DocumentChunk(
                    document_id=document_id,
                    page_number=tc.page_number,
                    chunk_index=tc.chunk_index,
                    content=tc.content,
                    summary=meta.summary or None,
                    extra_metadata=meta_dict,
                    embedding=embedding,
                )
                db_chunks.append(chunk)

                # Upsert concepts discovered in this chunk
                for concept_name in meta.concepts:
                    name = concept_name.strip()
                    if name:
                        await self.concepts.upsert(
                            exam_id=document.exam_id,
                            name=name,
                            description=meta.summary or None,
                        )

                if (tc.chunk_index + 1) % 5 == 0 or (tc.chunk_index + 1) == total:
                    logger.info(
                        "document_chunk_progress",
                        document_id=str(document_id),
                        done=tc.chunk_index + 1,
                        total=total,
                    )

            await self.chunks.bulk_create(db_chunks)

            document = await self.documents.update_status(
                document,
                DocumentStatus.PROCESSED,
                page_count=extracted.page_count,
                chunk_count=len(db_chunks),
            )
            logger.info(
                "document_processing_completed",
                document_id=str(document_id),
                pages=extracted.page_count,
                chunks=len(db_chunks),
            )
            return document

        except Exception as exc:
            logger.exception("document_processing_failed", document_id=str(document_id))
            # Integrity / flush errors leave the session needing a rollback before
            # we can persist FAILED status.
            await self.session.rollback()
            document = await self.get(document_id)
            await self.documents.update_status(
                document,
                DocumentStatus.FAILED,
                error_message=str(exc)[:2000],
            )
            if isinstance(exc, ProcessingError):
                raise
            raise ProcessingError(f"Document processing failed: {exc}") from exc

"""Unit tests for DocumentService with mocked collaborators."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import Settings
from app.core.exceptions import NotFoundError, ValidationError
from app.models.document import Document
from app.models.enums import DocumentStatus, DocumentType
from app.models.exam import Exam
from app.providers.chunking.semantic import SemanticChunker
from app.providers.embedding.mock import MockEmbeddingProvider
from app.providers.llm.mock import MockLLMProvider
from app.providers.pdf.base import ExtractedDocument, PageText
from app.schemas.document import DocumentUploadMeta
from app.services.document import DocumentService


def _make_service(
    settings: Settings,
    *,
    session: MagicMock | None = None,
) -> DocumentService:
    session = session or MagicMock()
    storage = MagicMock()
    storage.build_path.return_value = Path("/tmp/test.pdf")
    storage.save = AsyncMock(return_value=Path("/tmp/test.pdf"))

    pdf = MagicMock()
    pdf.extract = AsyncMock(
        return_value=ExtractedDocument(
            pages=[
                PageText(
                    page_number=1,
                    text=" ".join(
                        f"Sentence {i} about banking and finance for exam prep."
                        for i in range(40)
                    ),
                )
            ],
            page_count=1,
        )
    )

    return DocumentService(
        session,
        storage=storage,
        pdf_extractor=pdf,
        chunker=SemanticChunker(settings),
        llm=MockLLMProvider(),
        embeddings=MockEmbeddingProvider(dimension=settings.embedding_dimension),
        settings=settings,
    )


@pytest.mark.asyncio
async def test_upload_rejects_empty_file(settings: Settings) -> None:
    service = _make_service(settings)
    meta = DocumentUploadMeta(
        exam_id=uuid.uuid4(),
        title="Test",
        document_type=DocumentType.BOOK,
    )
    with pytest.raises(ValidationError):
        await service.upload(
            meta=meta,
            filename="x.pdf",
            content_type="application/pdf",
            data=b"",
        )


@pytest.mark.asyncio
async def test_upload_rejects_missing_exam(settings: Settings) -> None:
    service = _make_service(settings)
    service.exams.get_by_id = AsyncMock(return_value=None)
    meta = DocumentUploadMeta(
        exam_id=uuid.uuid4(),
        title="Test",
        document_type=DocumentType.SYLLABUS,
    )
    with pytest.raises(NotFoundError):
        await service.upload(
            meta=meta,
            filename="syllabus.pdf",
            content_type="application/pdf",
            data=b"%PDF-1.4",
        )


@pytest.mark.asyncio
async def test_upload_success(settings: Settings) -> None:
    service = _make_service(settings)
    exam_id = uuid.uuid4()
    service.exams.get_by_id = AsyncMock(
        return_value=Exam(id=exam_id, code="IBPS_PO", name="IBPS PO")
    )

    created = Document(
        id=uuid.uuid4(),
        exam_id=exam_id,
        title="Quant Book",
        document_type=DocumentType.BOOK,
        status=DocumentStatus.UPLOADED,
        filename="quant.pdf",
        storage_path="/tmp/test.pdf",
        content_type="application/pdf",
        file_size_bytes=8,
        extra_metadata={},
    )
    service.documents.create = AsyncMock(return_value=created)

    meta = DocumentUploadMeta(
        exam_id=exam_id,
        title="Quant Book",
        document_type=DocumentType.BOOK,
    )
    result = await service.upload(
        meta=meta,
        filename="quant.pdf",
        content_type="application/pdf",
        data=b"%PDF-1.4",
    )
    assert result.status == DocumentStatus.UPLOADED
    assert result.title == "Quant Book"
    service.storage.save.assert_awaited()


@pytest.mark.asyncio
async def test_mark_processing_blocks_processed(settings: Settings) -> None:
    service = _make_service(settings)
    doc = Document(
        id=uuid.uuid4(),
        exam_id=uuid.uuid4(),
        title="X",
        document_type=DocumentType.BOOK,
        status=DocumentStatus.PROCESSED,
        filename="x.pdf",
        storage_path="/tmp/x.pdf",
        content_type="application/pdf",
        file_size_bytes=1,
    )
    service.documents.get_by_id = AsyncMock(return_value=doc)
    with pytest.raises(ValidationError):
        await service.mark_processing(doc.id)

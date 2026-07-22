"""Document and DocumentChunk repositories."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.document import Document, DocumentChunk
from app.models.enums import DocumentStatus, DocumentType


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, document: Document) -> Document:
        self.session.add(document)
        await self.session.flush()
        await self.session.refresh(document)
        return document

    async def get_by_id(
        self, document_id: uuid.UUID, *, with_chunks: bool = False
    ) -> Document | None:
        if with_chunks:
            result = await self.session.execute(
                select(Document)
                .options(selectinload(Document.chunks))
                .where(Document.id == document_id)
            )
            return result.scalar_one_or_none()
        return await self.session.get(Document, document_id)

    async def list(
        self,
        *,
        exam_id: uuid.UUID | None = None,
        status: DocumentStatus | None = None,
        document_type: DocumentType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Document], int]:
        filters = []
        if exam_id is not None:
            filters.append(Document.exam_id == exam_id)
        if status is not None:
            filters.append(Document.status == status)
        if document_type is not None:
            filters.append(Document.document_type == document_type)

        count_stmt = select(func.count()).select_from(Document)
        list_stmt = select(Document).order_by(Document.created_at.desc()).limit(limit).offset(offset)
        if filters:
            count_stmt = count_stmt.where(*filters)
            list_stmt = list_stmt.where(*filters)

        total = int((await self.session.execute(count_stmt)).scalar_one())
        items = list((await self.session.execute(list_stmt)).scalars().all())
        return items, total

    async def update_status(
        self,
        document: Document,
        status: DocumentStatus,
        *,
        error_message: str | None = None,
        page_count: int | None = None,
        chunk_count: int | None = None,
    ) -> Document:
        document.status = status
        if error_message is not None:
            document.error_message = error_message
        if page_count is not None:
            document.page_count = page_count
        if chunk_count is not None:
            document.chunk_count = chunk_count
        if status == DocumentStatus.PROCESSED:
            document.processed_at = datetime.now(UTC)
            document.error_message = None
        await self.session.flush()
        await self.session.refresh(document)
        return document


class DocumentChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def bulk_create(self, chunks: list[DocumentChunk]) -> list[DocumentChunk]:
        self.session.add_all(chunks)
        await self.session.flush()
        for c in chunks:
            await self.session.refresh(c)
        return chunks

    async def delete_by_document(self, document_id: uuid.UUID) -> int:
        result = await self.session.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )
        return result.rowcount or 0

    async def list_by_document(
        self,
        document_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[DocumentChunk], int]:
        count_stmt = (
            select(func.count())
            .select_from(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
        )
        total = int((await self.session.execute(count_stmt)).scalar_one())
        stmt = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
            .limit(limit)
            .offset(offset)
        )
        items = list((await self.session.execute(stmt)).scalars().all())
        return items, total

    async def update_embedding_and_metadata(
        self,
        chunk: DocumentChunk,
        *,
        embedding: list[float],
        summary: str | None,
        metadata: dict[str, Any],
    ) -> DocumentChunk:
        chunk.embedding = embedding
        chunk.summary = summary
        chunk.extra_metadata = metadata
        await self.session.flush()
        return chunk

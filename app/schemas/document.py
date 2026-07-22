"""Pydantic schemas for documents and chunks."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import DocumentStatus, DocumentType


class DocumentUploadMeta(BaseModel):
    exam_id: uuid.UUID
    title: str = Field(..., min_length=1, max_length=512)
    document_type: DocumentType
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentRead(BaseModel):
    """
    Response DTO for documents.

    Note: SQLAlchemy's DeclarativeBase exposes `.metadata` (MetaData registry).
    Our JSON column is mapped as `extra_metadata`, so we read that attribute
    and expose it in the API as `metadata`.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    exam_id: uuid.UUID
    title: str
    document_type: DocumentType
    status: DocumentStatus
    filename: str
    content_type: str
    file_size_bytes: int
    page_count: int | None = None
    chunk_count: int = 0
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    processed_at: datetime | None = None

    @field_validator("metadata", mode="before")
    @classmethod
    def coerce_metadata(cls, value: Any) -> dict[str, Any]:
        # Guard against accidental SQLAlchemy MetaData leakage
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        return {}

    @classmethod
    def model_validate(cls, obj: Any, **kwargs: Any) -> DocumentRead:  # type: ignore[override]
        if hasattr(obj, "extra_metadata"):
            data = {
                "id": obj.id,
                "exam_id": obj.exam_id,
                "title": obj.title,
                "document_type": obj.document_type,
                "status": obj.status,
                "filename": obj.filename,
                "content_type": obj.content_type,
                "file_size_bytes": obj.file_size_bytes,
                "page_count": obj.page_count,
                "chunk_count": obj.chunk_count or 0,
                "error_message": obj.error_message,
                "metadata": obj.extra_metadata or {},
                "created_at": obj.created_at,
                "updated_at": obj.updated_at,
                "processed_at": obj.processed_at,
            }
            return super().model_validate(data, **kwargs)
        return super().model_validate(obj, **kwargs)


class DocumentListResponse(BaseModel):
    items: list[DocumentRead]
    total: int
    limit: int
    offset: int


class DocumentProcessResponse(BaseModel):
    document_id: uuid.UUID
    status: DocumentStatus
    message: str


class ChunkMetadata(BaseModel):
    """LLM-extracted metadata for a document chunk."""

    subject: str = ""
    chapter: str = ""
    topic: str = ""
    subtopics: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)
    learningObjectives: list[str] = Field(default_factory=list)
    summary: str = ""
    difficultyHint: str = ""
    sourceType: str = ""

    @field_validator(
        "subject",
        "chapter",
        "topic",
        "summary",
        "difficultyHint",
        "sourceType",
        mode="before",
    )
    @classmethod
    def coerce_str_fields(cls, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, list):
            parts = [str(v).strip() for v in value if str(v).strip()]
            return ", ".join(parts)
        return str(value).strip()

    @field_validator(
        "subtopics",
        "keywords",
        "concepts",
        "learningObjectives",
        mode="before",
    )
    @classmethod
    def coerce_list_fields(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        return [str(value).strip()]


class DocumentChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    document_id: uuid.UUID
    page_number: int
    chunk_index: int
    content: str
    summary: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    @classmethod
    def model_validate(cls, obj: Any, **kwargs: Any) -> DocumentChunkRead:  # type: ignore[override]
        if hasattr(obj, "extra_metadata"):
            data = {
                "id": obj.id,
                "document_id": obj.document_id,
                "page_number": obj.page_number,
                "chunk_index": obj.chunk_index,
                "content": obj.content,
                "summary": obj.summary,
                "metadata": obj.extra_metadata or {},
                "created_at": obj.created_at,
            }
            return super().model_validate(data, **kwargs)
        return super().model_validate(obj, **kwargs)


class DocumentChunkListResponse(BaseModel):
    items: list[DocumentChunkRead]
    total: int
    limit: int
    offset: int

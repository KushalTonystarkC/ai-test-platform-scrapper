"""Search request/response schemas."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import SearchMode


class SearchQuery(BaseModel):
    q: str = Field(..., min_length=1, max_length=2000)
    mode: SearchMode = SearchMode.HYBRID
    exam_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    limit: int = Field(default=10, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class SearchHit(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    page_number: int
    chunk_index: int
    content: str
    summary: str | None
    metadata: dict[str, Any]
    score: float
    keyword_score: float | None = None
    semantic_score: float | None = None


class SearchResponse(BaseModel):
    query: str
    mode: SearchMode
    items: list[SearchHit]
    total: int

"""Search REST endpoint."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from app.core.dependencies import SearchServiceDep
from app.models.enums import SearchMode
from app.schemas.search import SearchQuery, SearchResponse

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse)
async def search(
    service: SearchServiceDep,
    q: str = Query(..., min_length=1, max_length=2000),
    mode: SearchMode = Query(default=SearchMode.HYBRID),
    exam_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> SearchResponse:
    query = SearchQuery(
        q=q,
        mode=mode,
        exam_id=exam_id,
        document_id=document_id,
        limit=limit,
        offset=offset,
    )
    return await service.search(query)

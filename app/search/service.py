"""Keyword, semantic, and hybrid search over document chunks."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.models.document import Document, DocumentChunk
from app.models.enums import SearchMode
from app.providers.embedding.base import EmbeddingProvider
from app.schemas.search import SearchHit, SearchQuery, SearchResponse

logger = get_logger(__name__)


class SearchService:
    """
    Search implementation using PostgreSQL FTS + pgvector.

    Business-facing entry point reusable by REST, MCP, CLI, and workers.
    """

    def __init__(
        self,
        session: AsyncSession,
        embedding_provider: EmbeddingProvider,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.embedding_provider = embedding_provider
        self.settings = settings or get_settings()

    async def search(self, query: SearchQuery) -> SearchResponse:
        if query.mode == SearchMode.KEYWORD:
            hits = await self.keyword_search(query)
        elif query.mode == SearchMode.SEMANTIC:
            hits = await self.semantic_search(query)
        else:
            hits = await self.hybrid_search(query)

        return SearchResponse(
            query=query.q,
            mode=query.mode,
            items=hits,
            total=len(hits),
        )

    async def keyword_search(self, query: SearchQuery) -> list[SearchHit]:
        """Full-text search using PostgreSQL `to_tsvector` / `plainto_tsquery`."""
        stmt = self._base_chunk_select(query)
        # Ranking via ts_rank
        rank = func.ts_rank(
            func.to_tsvector("english", DocumentChunk.content),
            func.plainto_tsquery("english", query.q),
        ).label("keyword_score")

        stmt = (
            stmt.add_columns(rank)
            .where(
                func.to_tsvector("english", DocumentChunk.content).op("@@")(
                    func.plainto_tsquery("english", query.q)
                )
            )
            .order_by(rank.desc())
            .limit(query.limit)
            .offset(query.offset)
        )

        result = await self.session.execute(stmt)
        rows = result.all()
        return [
            self._to_hit(chunk, score=float(kw_score or 0), keyword_score=float(kw_score or 0))
            for chunk, kw_score in rows
        ]

    async def semantic_search(self, query: SearchQuery) -> list[SearchHit]:
        """Nearest-neighbor search via pgvector cosine distance."""
        vector = await self.embedding_provider.generate_embedding(query.q)
        distance = DocumentChunk.embedding.cosine_distance(vector).label("distance")

        stmt = self._base_chunk_select(query)
        stmt = (
            stmt.add_columns(distance)
            .where(DocumentChunk.embedding.is_not(None))
            .order_by(distance)
            .limit(query.limit)
            .offset(query.offset)
        )

        result = await self.session.execute(stmt)
        rows = result.all()
        hits: list[SearchHit] = []
        for chunk, dist in rows:
            # cosine distance ∈ [0, 2] → similarity score ∈ [0, 1]
            sim = max(0.0, 1.0 - float(dist))
            hits.append(self._to_hit(chunk, score=sim, semantic_score=sim))
        return hits

    async def hybrid_search(self, query: SearchQuery) -> list[SearchHit]:
        """
        Reciprocal-style fusion of keyword and semantic scores.

        Fetches a wider candidate set from each channel, normalizes scores,
        then blends with configured weights.
        """
        candidate_limit = max(query.limit * 3, 30)
        kw_query = query.model_copy(update={"limit": candidate_limit, "offset": 0})
        sem_query = query.model_copy(update={"limit": candidate_limit, "offset": 0})

        keyword_hits = await self.keyword_search(kw_query)
        semantic_hits = await self.semantic_search(sem_query)

        kw_weight = self.settings.hybrid_keyword_weight
        sem_weight = self.settings.hybrid_semantic_weight

        merged: dict[uuid.UUID, SearchHit] = {}

        def _norm(scores: list[float]) -> dict[int, float]:
            if not scores:
                return {}
            mx = max(scores) or 1.0
            return {i: s / mx for i, s in enumerate(scores)}

        kw_norms = _norm([h.score for h in keyword_hits])
        sem_norms = _norm([h.score for h in semantic_hits])

        for i, hit in enumerate(keyword_hits):
            n = kw_norms.get(i, 0.0)
            existing = merged.get(hit.chunk_id)
            if existing:
                existing.keyword_score = n
                existing.score = (existing.semantic_score or 0) * sem_weight + n * kw_weight
            else:
                merged[hit.chunk_id] = hit.model_copy(
                    update={
                        "keyword_score": n,
                        "semantic_score": 0.0,
                        "score": n * kw_weight,
                    }
                )

        for i, hit in enumerate(semantic_hits):
            n = sem_norms.get(i, 0.0)
            existing = merged.get(hit.chunk_id)
            if existing:
                existing.semantic_score = n
                existing.score = n * sem_weight + (existing.keyword_score or 0) * kw_weight
            else:
                merged[hit.chunk_id] = hit.model_copy(
                    update={
                        "semantic_score": n,
                        "keyword_score": 0.0,
                        "score": n * sem_weight,
                    }
                )

        ranked = sorted(merged.values(), key=lambda h: h.score, reverse=True)
        start = query.offset
        end = start + query.limit
        return ranked[start:end]

    def _base_chunk_select(self, query: SearchQuery) -> Select[Any]:
        stmt = select(DocumentChunk).join(Document, Document.id == DocumentChunk.document_id)
        if query.exam_id is not None:
            stmt = stmt.where(Document.exam_id == query.exam_id)
        if query.document_id is not None:
            stmt = stmt.where(DocumentChunk.document_id == query.document_id)
        return stmt

    @staticmethod
    def _to_hit(
        chunk: DocumentChunk,
        *,
        score: float,
        keyword_score: float | None = None,
        semantic_score: float | None = None,
    ) -> SearchHit:
        return SearchHit(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            page_number=chunk.page_number,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            summary=chunk.summary,
            metadata=chunk.extra_metadata or {},
            score=score,
            keyword_score=keyword_score,
            semantic_score=semantic_score,
        )

"""KnowledgeConcept repository."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeConcept


class KnowledgeConceptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(
        self,
        *,
        exam_id: uuid.UUID,
        name: str,
        description: str | None = None,
        subject_id: uuid.UUID | None = None,
        aliases: list[str] | None = None,
    ) -> KnowledgeConcept:
        existing = await self.get_by_exam_and_name(exam_id, name)
        if existing:
            if description and not existing.description:
                existing.description = description
            if aliases:
                merged = list(dict.fromkeys([*(existing.aliases or []), *aliases]))
                existing.aliases = merged
            if subject_id and not existing.subject_id:
                existing.subject_id = subject_id
            await self.session.flush()
            return existing

        concept = KnowledgeConcept(
            exam_id=exam_id,
            name=name,
            description=description,
            subject_id=subject_id,
            aliases=aliases or [],
        )
        self.session.add(concept)
        await self.session.flush()
        await self.session.refresh(concept)
        return concept

    async def get_by_exam_and_name(
        self, exam_id: uuid.UUID, name: str
    ) -> KnowledgeConcept | None:
        result = await self.session.execute(
            select(KnowledgeConcept).where(
                KnowledgeConcept.exam_id == exam_id,
                KnowledgeConcept.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_exam(
        self, exam_id: uuid.UUID, *, limit: int = 200, offset: int = 0
    ) -> list[KnowledgeConcept]:
        result = await self.session.execute(
            select(KnowledgeConcept)
            .where(KnowledgeConcept.exam_id == exam_id)
            .order_by(KnowledgeConcept.name)
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

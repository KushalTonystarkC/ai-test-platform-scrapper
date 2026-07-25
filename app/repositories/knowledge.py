"""KnowledgeConcept repository."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
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
        """Insert or update a concept; safe under concurrent document processors."""
        aliases = aliases or []
        stmt = (
            insert(KnowledgeConcept)
            .values(
                id=uuid.uuid4(),
                exam_id=exam_id,
                name=name,
                description=description,
                subject_id=subject_id,
                aliases=aliases,
                extra_metadata={},
            )
            .on_conflict_do_nothing(constraint="uq_concepts_exam_name")
        )
        await self.session.execute(stmt)

        # After a concurrent winner commits, ON CONFLICT DO NOTHING leaves us
        # without a local INSERT — re-select (brief retry for visibility).
        existing = await self.get_by_exam_and_name(exam_id, name)
        if existing is None:
            await self.session.flush()
            existing = await self.get_by_exam_and_name(exam_id, name)
        if existing is None:
            raise RuntimeError(
                f"Concept upsert failed for exam={exam_id} name={name!r}"
            )

        changed = False
        if description and not existing.description:
            existing.description = description
            changed = True
        if aliases:
            merged = list(dict.fromkeys([*(existing.aliases or []), *aliases]))
            if merged != (existing.aliases or []):
                existing.aliases = merged
                changed = True
        if subject_id and not existing.subject_id:
            existing.subject_id = subject_id
            changed = True
        if changed:
            await self.session.flush()
        return existing

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

"""Question repository."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question import Question


class QuestionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, question: Question) -> Question:
        self.session.add(question)
        await self.session.flush()
        await self.session.refresh(question)
        return question

    async def bulk_create(self, questions: list[Question]) -> list[Question]:
        if not questions:
            return []
        self.session.add_all(questions)
        await self.session.flush()
        for q in questions:
            await self.session.refresh(q)
        return questions

    async def get_by_id(self, question_id: uuid.UUID) -> Question | None:
        return await self.session.get(Question, question_id)

    async def delete_by_id(self, question_id: uuid.UUID) -> bool:
        question = await self.get_by_id(question_id)
        if not question:
            return False
        await self.session.delete(question)
        await self.session.flush()
        return True

    async def delete_all(
        self,
        *,
        exam_id: uuid.UUID | None = None,
    ) -> int:
        stmt = delete(Question)
        if exam_id is not None:
            stmt = stmt.where(Question.exam_id == exam_id)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return int(result.rowcount or 0)

    async def list(
        self,
        *,
        exam_id: uuid.UUID | None = None,
        difficulty: str | None = None,
        topic: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Question], int]:
        filters = []
        if exam_id is not None:
            filters.append(Question.exam_id == exam_id)
        if difficulty:
            filters.append(Question.difficulty == difficulty)
        if topic:
            filters.append(Question.topic.ilike(f"%{topic}%"))

        count_stmt = select(func.count()).select_from(Question)
        list_stmt = select(Question).order_by(Question.created_at.desc()).limit(limit).offset(offset)
        if filters:
            count_stmt = count_stmt.where(*filters)
            list_stmt = list_stmt.where(*filters)

        total = int((await self.session.execute(count_stmt)).scalar_one())
        rows = list((await self.session.execute(list_stmt)).scalars().all())
        return rows, total

    async def list_stems(
        self,
        *,
        exam_id: uuid.UUID,
        document_id: uuid.UUID | None = None,
        topic: str | None = None,
        limit: int = 500,
    ) -> list[str]:
        """Return existing question stems for duplicate checks during generation."""
        filters = [Question.exam_id == exam_id]
        if document_id is not None:
            filters.append(Question.document_id == document_id)
        if topic:
            filters.append(Question.topic.ilike(f"%{topic}%"))

        stmt = (
            select(Question.stem)
            .where(*filters)
            .order_by(Question.created_at.desc())
            .limit(limit)
        )
        return [str(stem) for stem in (await self.session.execute(stmt)).scalars().all()]
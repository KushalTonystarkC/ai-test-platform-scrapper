"""Exam and Subject repositories."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exam import Exam, Subject


class ExamRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, exam: Exam) -> Exam:
        self.session.add(exam)
        await self.session.flush()
        await self.session.refresh(exam)
        return exam

    async def get_by_id(self, exam_id: uuid.UUID) -> Exam | None:
        return await self.session.get(Exam, exam_id)

    async def get_by_code(self, code: str) -> Exam | None:
        result = await self.session.execute(select(Exam).where(Exam.code == code))
        return result.scalar_one_or_none()

    async def list(
        self, *, active_only: bool = False, limit: int = 100, offset: int = 0
    ) -> list[Exam]:
        stmt = select(Exam).order_by(Exam.code).limit(limit).offset(offset)
        if active_only:
            stmt = stmt.where(Exam.is_active.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update(self, exam: Exam) -> Exam:
        await self.session.flush()
        await self.session.refresh(exam)
        return exam


class SubjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, subject: Subject) -> Subject:
        self.session.add(subject)
        await self.session.flush()
        await self.session.refresh(subject)
        return subject

    async def get_by_id(self, subject_id: uuid.UUID) -> Subject | None:
        return await self.session.get(Subject, subject_id)

    async def list_by_exam(self, exam_id: uuid.UUID) -> list[Subject]:
        result = await self.session.execute(
            select(Subject).where(Subject.exam_id == exam_id).order_by(Subject.code)
        )
        return list(result.scalars().all())

    async def get_by_exam_and_code(self, exam_id: uuid.UUID, code: str) -> Subject | None:
        result = await self.session.execute(
            select(Subject).where(Subject.exam_id == exam_id, Subject.code == code)
        )
        return result.scalar_one_or_none()

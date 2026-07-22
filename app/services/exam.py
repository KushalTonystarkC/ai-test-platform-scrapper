"""Exam management service."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.exam import Exam, Subject
from app.repositories.exam import ExamRepository, SubjectRepository
from app.schemas.exam import ExamCreate, ExamUpdate, SubjectCreate


class ExamService:
    def __init__(self, session: AsyncSession) -> None:
        self.exams = ExamRepository(session)
        self.subjects = SubjectRepository(session)

    async def create_exam(self, data: ExamCreate) -> Exam:
        existing = await self.exams.get_by_code(data.code)
        if existing:
            raise ConflictError(
                f"Exam with code '{data.code}' already exists",
                details={"exam_id": str(existing.id)},
            )
        exam = Exam(
            code=data.code.upper(),
            name=data.name,
            description=data.description,
            is_active=data.is_active,
        )
        return await self.exams.create(exam)

    async def get_exam(self, exam_id: uuid.UUID) -> Exam:
        exam = await self.exams.get_by_id(exam_id)
        if not exam:
            raise NotFoundError(f"Exam {exam_id} not found")
        return exam

    async def list_exams(self, *, active_only: bool = False) -> list[Exam]:
        return await self.exams.list(active_only=active_only)

    async def update_exam(self, exam_id: uuid.UUID, data: ExamUpdate) -> Exam:
        exam = await self.get_exam(exam_id)
        payload = data.model_dump(exclude_unset=True)
        for key, value in payload.items():
            setattr(exam, key, value)
        return await self.exams.update(exam)

    async def create_subject(self, data: SubjectCreate) -> Subject:
        await self.get_exam(data.exam_id)
        existing = await self.subjects.get_by_exam_and_code(data.exam_id, data.code)
        if existing:
            raise ConflictError(f"Subject '{data.code}' already exists for this exam")
        subject = Subject(
            exam_id=data.exam_id,
            code=data.code.upper(),
            name=data.name,
            description=data.description,
        )
        return await self.subjects.create(subject)

    async def list_subjects(self, exam_id: uuid.UUID) -> list[Subject]:
        await self.get_exam(exam_id)
        return await self.subjects.list_by_exam(exam_id)

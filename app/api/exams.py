"""Exam REST endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from app.core.dependencies import ExamServiceDep
from app.schemas.exam import ExamCreate, ExamRead, ExamUpdate, SubjectCreate, SubjectRead

router = APIRouter(prefix="/exams", tags=["exams"])


@router.post("", response_model=ExamRead, status_code=201)
async def create_exam(payload: ExamCreate, service: ExamServiceDep) -> ExamRead:
    exam = await service.create_exam(payload)
    return ExamRead.model_validate(exam)


@router.get("", response_model=list[ExamRead])
async def list_exams(
    service: ExamServiceDep,
    active_only: bool = Query(default=False),
) -> list[ExamRead]:
    exams = await service.list_exams(active_only=active_only)
    return [ExamRead.model_validate(e) for e in exams]


@router.get("/{exam_id}", response_model=ExamRead)
async def get_exam(exam_id: uuid.UUID, service: ExamServiceDep) -> ExamRead:
    exam = await service.get_exam(exam_id)
    return ExamRead.model_validate(exam)


@router.patch("/{exam_id}", response_model=ExamRead)
async def update_exam(
    exam_id: uuid.UUID, payload: ExamUpdate, service: ExamServiceDep
) -> ExamRead:
    exam = await service.update_exam(exam_id, payload)
    return ExamRead.model_validate(exam)


@router.post("/{exam_id}/subjects", response_model=SubjectRead, status_code=201)
async def create_subject(
    exam_id: uuid.UUID, payload: SubjectCreate, service: ExamServiceDep
) -> SubjectRead:
    # Ensure path exam_id matches body
    data = payload.model_copy(update={"exam_id": exam_id})
    subject = await service.create_subject(data)
    return SubjectRead.model_validate(subject)


@router.get("/{exam_id}/subjects", response_model=list[SubjectRead])
async def list_subjects(exam_id: uuid.UUID, service: ExamServiceDep) -> list[SubjectRead]:
    subjects = await service.list_subjects(exam_id)
    return [SubjectRead.model_validate(s) for s in subjects]

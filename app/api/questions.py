"""Question REST endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from app.core.dependencies import DbSession, QuestionServiceDep
from app.schemas.question import (
    GenerateQuestionRequest,
    GenerateQuestionResponse,
    QuestionListResponse,
    QuestionRead,
)

router = APIRouter(prefix="/questions", tags=["questions"])


@router.post("/generate", response_model=GenerateQuestionResponse)
async def generate_questions(
    payload: GenerateQuestionRequest,
    service: QuestionServiceDep,
    session: DbSession,
) -> GenerateQuestionResponse:
    items, context_used, mode = await service.generate(payload)
    await session.commit()
    return GenerateQuestionResponse(
        exam_id=payload.exam_id,
        topic=payload.topic,
        mode=mode,
        requested_count=payload.count,
        generated_count=len(items),
        context_used=context_used,
        items=[QuestionRead.model_validate(q) for q in items],
    )


@router.get("", response_model=QuestionListResponse)
async def list_questions(
    service: QuestionServiceDep,
    exam_id: uuid.UUID | None = None,
    difficulty: str | None = Query(default=None),
    topic: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> QuestionListResponse:
    items, total = await service.list(
        exam_id=exam_id,
        difficulty=difficulty,
        topic=topic,
        limit=limit,
        offset=offset,
    )
    return QuestionListResponse(
        items=[QuestionRead.model_validate(q) for q in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{question_id}", response_model=QuestionRead)
async def get_question(question_id: uuid.UUID, service: QuestionServiceDep) -> QuestionRead:
    question = await service.get(question_id)
    return QuestionRead.model_validate(question)

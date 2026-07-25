"""Question REST endpoints."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.dependencies import DbSession, QuestionServiceDep
from app.core.exceptions import AppError
from app.schemas.question import (
    GenerateQuestionRequest,
    GenerateQuestionResponse,
    QuestionListResponse,
    QuestionRead,
)

router = APIRouter(prefix="/questions", tags=["questions"])


class ClearQuestionsResponse(BaseModel):
    deleted_count: int = Field(..., ge=0)
    exam_id: uuid.UUID | None = None


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.post("/generate", response_model=GenerateQuestionResponse)
async def generate_questions(
    payload: GenerateQuestionRequest,
    service: QuestionServiceDep,
    session: DbSession,
) -> GenerateQuestionResponse:
    items, context_used, mode, question_type = await service.generate(payload)
    await session.commit()
    return GenerateQuestionResponse(
        exam_id=payload.exam_id,
        topic=payload.topic,
        mode=mode,
        question_type=question_type,
        requested_count=payload.count,
        generated_count=len(items),
        context_used=context_used,
        items=[QuestionRead.model_validate(q) for q in items],
    )


@router.post("/generate/stream")
async def generate_questions_stream(
    payload: GenerateQuestionRequest,
    service: QuestionServiceDep,
    session: DbSession,
) -> StreamingResponse:
    """Stream MCQ generation progress as Server-Sent Events."""

    async def event_source() -> AsyncIterator[str]:
        try:
            async for event in service.generate_events(payload, persist=True):
                name = str(event.get("event") or "message")
                # Don't serialize the ORM object over the wire
                data = {k: v for k, v in event.items() if k != "question"}
                yield _sse(name, data)
                if name == "question":
                    await session.commit()
                if name == "done":
                    await session.commit()
                if name == "error":
                    await session.rollback()
        except AppError as exc:
            await session.rollback()
            yield _sse(
                "error",
                {
                    "error": exc.message,
                    "code": getattr(exc, "code", None),
                },
            )
        except Exception as exc:  # pragma: no cover - defensive
            await session.rollback()
            yield _sse("error", {"error": str(exc)})

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
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


@router.delete("", response_model=ClearQuestionsResponse)
async def clear_questions(
    service: QuestionServiceDep,
    session: DbSession,
    exam_id: uuid.UUID | None = None,
) -> ClearQuestionsResponse:
    deleted = await service.clear(exam_id=exam_id)
    await session.commit()
    return ClearQuestionsResponse(deleted_count=deleted, exam_id=exam_id)


@router.get("/{question_id}", response_model=QuestionRead)
async def get_question(question_id: uuid.UUID, service: QuestionServiceDep) -> QuestionRead:
    question = await service.get(question_id)
    return QuestionRead.model_validate(question)


@router.delete("/{question_id}", status_code=204)
async def delete_question(
    question_id: uuid.UUID,
    service: QuestionServiceDep,
    session: DbSession,
) -> None:
    await service.delete(question_id)
    await session.commit()

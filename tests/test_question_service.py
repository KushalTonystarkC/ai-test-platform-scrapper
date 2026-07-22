"""Unit tests for question schemas and QuestionService."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import NotFoundError, ValidationError
from app.models.exam import Exam
from app.models.question import Question
from app.schemas.question import GeneratedMCQ, GenerateQuestionRequest, QuestionRead
from app.schemas.search import SearchHit, SearchResponse
from app.services.question import QuestionService
from app.models.enums import SearchMode


def test_generated_mcq_requires_four_options() -> None:
    with pytest.raises(PydanticValidationError):
        GeneratedMCQ(
            stem="Q?",
            options=["a", "b", "c"],
            correct_index=0,
        )


def test_generated_mcq_rejects_empty_option() -> None:
    with pytest.raises(PydanticValidationError):
        GeneratedMCQ(
            stem="Q?",
            options=["a", "b", "", "d"],
            correct_index=1,
        )


def test_generated_mcq_ok() -> None:
    mcq = GeneratedMCQ(
        stem="Who regulates banks?",
        options=["SEBI", "RBI", "IRDAI", "NABARD"],
        correct_index=1,
        difficulty="EASY",  # type: ignore[arg-type]
    )
    assert mcq.difficulty == "easy"
    assert mcq.correct_index == 1


def test_question_read_from_orm_shape() -> None:
    q = Question(
        id=uuid.uuid4(),
        exam_id=uuid.uuid4(),
        stem="Stem?",
        options=["A", "B", "C", "D"],
        correct_index=2,
        explanation="Because C",
        subject="Banking",
        topic="RBI",
        difficulty="medium",
        source_chunk_ids=[str(uuid.uuid4())],
        extra_metadata={"exam_code": "IBPS_PO"},
        created_at=datetime.now(timezone.utc),
    )
    read = QuestionRead.model_validate(q)
    assert read.stem == "Stem?"
    assert len(read.options) == 4
    assert read.metadata["exam_code"] == "IBPS_PO"


def _make_service() -> QuestionService:
    session = MagicMock()
    llm = MagicMock()
    search = MagicMock()
    return QuestionService(session, llm=llm, search=search)


@pytest.mark.asyncio
async def test_generate_raises_when_exam_missing() -> None:
    service = _make_service()
    service.exams.get_by_id = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await service.generate(
            GenerateQuestionRequest(exam_id=uuid.uuid4(), topic="RBI")
        )


@pytest.mark.asyncio
async def test_generate_raises_when_no_chunks() -> None:
    service = _make_service()
    exam_id = uuid.uuid4()
    service.exams.get_by_id = AsyncMock(
        return_value=Exam(id=exam_id, code="IBPS_PO", name="IBPS PO")
    )
    service.search.search = AsyncMock(
        return_value=SearchResponse(query="RBI", mode=SearchMode.HYBRID, items=[], total=0)
    )
    with pytest.raises(ValidationError, match="No knowledge-base chunks"):
        await service.generate(GenerateQuestionRequest(exam_id=exam_id, topic="RBI"))


@pytest.mark.asyncio
async def test_generate_persists_valid_mcqs() -> None:
    service = _make_service()
    exam_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    service.exams.get_by_id = AsyncMock(
        return_value=Exam(id=exam_id, code="IBPS_PO", name="IBPS PO")
    )
    service.search.search = AsyncMock(
        return_value=SearchResponse(
            query="RBI",
            mode=SearchMode.HYBRID,
            items=[
                SearchHit(
                    chunk_id=chunk_id,
                    document_id=uuid.uuid4(),
                    page_number=1,
                    chunk_index=0,
                    content="RBI regulates banks in India.",
                    summary="RBI regulates banks.",
                    metadata={},
                    score=0.9,
                )
            ],
            total=1,
        )
    )
    service.llm.generate_json = AsyncMock(
        return_value={
            "questions": [
                {
                    "stem": "Which institution regulates banks in India?",
                    "options": ["SEBI", "RBI", "IRDAI", "NABARD"],
                    "correct_index": 1,
                    "explanation": "RBI is the regulator.",
                    "subject": "Banking Awareness",
                    "topic": "RBI",
                    "difficulty": "easy",
                }
            ]
        }
    )

    async def _bulk(rows: list[Question]) -> list[Question]:
        for r in rows:
            r.created_at = datetime.now(timezone.utc)
        return rows

    service.questions.bulk_create = AsyncMock(side_effect=_bulk)

    saved, context_used = await service.generate(
        GenerateQuestionRequest(
            exam_id=exam_id,
            topic="RBI",
            count=1,
            subject="Banking Awareness",
        )
    )
    assert context_used == 1
    assert len(saved) == 1
    assert saved[0].correct_index == 1
    assert saved[0].options[1] == "RBI"
    service.questions.bulk_create.assert_awaited()

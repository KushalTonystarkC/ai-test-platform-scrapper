"""Unit tests for question schemas and QuestionService."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import NotFoundError, ValidationError
from app.models.document import DocumentChunk
from app.models.enums import SearchMode
from app.models.exam import Exam
from app.models.question import Question
from app.schemas.question import GeneratedMCQ, GenerateQuestionRequest, QuestionRead
from app.schemas.search import SearchHit, SearchResponse
from app.services.question import QuestionService


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


def test_generated_mcq_normalizes_word_token_options() -> None:
    words = (
        "Regulates banks and monetary policy in India and also handles "
        "currency issuance and foreign exchange management under statute"
    ).split()
    assert len(words) > 4
    mcq = GeneratedMCQ(
        stem="What does RBI do?",
        options=words,
        correct_index=0,
    )
    assert len(mcq.options) == 4
    assert all(mcq.options)


def test_generated_mcq_parses_letter_correct_index() -> None:
    mcq = GeneratedMCQ(
        stem="Q?",
        options=["A1", "B1", "C1", "D1"],
        correct_index="B",  # type: ignore[arg-type]
    )
    assert mcq.correct_index == 1


def test_generated_mcq_defaults_missing_correct_index() -> None:
    mcq = GeneratedMCQ.model_validate(
        {
            "stem": "Required probability concept?",
            "options": ["Mean", "Variance", "Mode", "Range"],
            "topic": "full_syllabus",
            "subject": "Quant",
        }
    )
    assert mcq.correct_index == 0
    assert mcq.stem.startswith("Required")


def test_generated_mcq_maps_answer_letter() -> None:
    mcq = GeneratedMCQ.model_validate(
        {
            "stem": "Q?",
            "options": ["A1", "B1", "C1", "D1"],
            "answer": "C",
        }
    )
    assert mcq.correct_index == 2


def test_topic_optional_and_blank_becomes_none() -> None:
    req = GenerateQuestionRequest(exam_id=uuid.uuid4(), topic="  ")
    assert req.topic is None
    req2 = GenerateQuestionRequest(exam_id=uuid.uuid4())
    assert req2.topic is None


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
    service = QuestionService(session, llm=llm, search=search)
    service.questions.list_stems = AsyncMock(return_value=[])
    return service


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
async def test_generate_topic_mode_persists() -> None:
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

    async def _create(row: Question) -> Question:
        row.created_at = datetime.now(timezone.utc)
        return row

    service.questions.create = AsyncMock(side_effect=_create)

    saved, context_used, mode, question_type = await service.generate(
        GenerateQuestionRequest(
            exam_id=exam_id,
            topic="RBI",
            count=1,
            subject="Banking Awareness",
        )
    )
    assert mode == "topic"
    assert question_type == "standalone"
    assert context_used == 1
    assert len(saved) == 1
    assert saved[0].correct_index == 1
    service.questions.create.assert_awaited()
    service.questions.list_stems.assert_awaited()


@pytest.mark.asyncio
async def test_generate_full_syllabus_samples_chunks() -> None:
    service = _make_service()
    exam_id = uuid.uuid4()
    chunk = DocumentChunk(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        page_number=1,
        chunk_index=0,
        content="Syllabus covers banking, quant, and reasoning.",
        summary="Full syllabus overview.",
        extra_metadata={},
    )
    service.exams.get_by_id = AsyncMock(
        return_value=Exam(id=exam_id, code="IBPS_PO", name="IBPS PO")
    )
    service.chunks.sample_for_exam = AsyncMock(return_value=[chunk])
    service.llm.generate_json = AsyncMock(
        return_value={
            "questions": [
                {
                    "stem": "Which area is part of the exam syllabus?",
                    "options": ["Cooking", "Banking Awareness", "Poetry", "Sports trivia"],
                    "correct_index": 1,
                    "explanation": "Banking is in the corpus.",
                    "subject": "Banking Awareness",
                    "topic": "syllabus",
                    "difficulty": "easy",
                }
            ]
        }
    )

    async def _create(row: Question) -> Question:
        row.created_at = datetime.now(timezone.utc)
        return row

    service.questions.create = AsyncMock(side_effect=_create)

    saved, context_used, mode, _ = await service.generate(
        GenerateQuestionRequest(exam_id=exam_id, count=1)
    )
    assert mode == "full_syllabus"
    assert context_used == 1
    assert saved[0].topic == "syllabus"
    assert saved[0].extra_metadata["generation_mode"] == "full_syllabus"
    service.chunks.sample_for_exam.assert_awaited()
    service.search.search.assert_not_called()


@pytest.mark.asyncio
async def test_generate_skips_stems_already_in_db() -> None:
    service = _make_service()
    exam_id = uuid.uuid4()
    existing = "Which institution regulates banks in India?"
    service.questions.list_stems = AsyncMock(return_value=[existing])
    service.exams.get_by_id = AsyncMock(
        return_value=Exam(id=exam_id, code="IBPS_PO", name="IBPS PO")
    )
    service.search.search = AsyncMock(
        return_value=SearchResponse(
            query="RBI",
            mode=SearchMode.HYBRID,
            items=[
                SearchHit(
                    chunk_id=uuid.uuid4(),
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
    # First attempt duplicates DB stem; second attempt is unique.
    service.llm.generate_json = AsyncMock(
        side_effect=[
            {
                "stem": existing,
                "options": ["SEBI", "RBI", "IRDAI", "NABARD"],
                "correct_index": 1,
                "explanation": "dup",
                "subject": "Banking",
                "topic": "RBI",
                "difficulty": "easy",
            },
            {
                "stem": "Who issues currency notes in India?",
                "options": ["SEBI", "RBI", "IRDAI", "NABARD"],
                "correct_index": 1,
                "explanation": "RBI issues notes.",
                "subject": "Banking",
                "topic": "RBI",
                "difficulty": "easy",
            },
        ]
    )

    async def _create(row: Question) -> Question:
        row.created_at = datetime.now(timezone.utc)
        return row

    service.questions.create = AsyncMock(side_effect=_create)

    saved, _, _, _ = await service.generate(
        GenerateQuestionRequest(exam_id=exam_id, topic="RBI", count=1)
    )
    assert len(saved) == 1
    assert saved[0].stem == "Who issues currency notes in India?"
    assert service.llm.generate_json.await_count == 2


def _passage_hit(content: str) -> SearchHit:
    return SearchHit(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        page_number=1,
        chunk_index=0,
        content=content,
        summary=None,
        metadata={},
        score=0.9,
    )


def test_plan_batches_splits_sets_and_folds_short_tail() -> None:
    assert QuestionService._plan_batches(
        3, question_type="standalone", set_size=3
    ) == [1, 1, 1]
    assert QuestionService._plan_batches(
        6, question_type="comprehension", set_size=3
    ) == [3, 3]
    # A trailing single question is folded into the previous set.
    assert QuestionService._plan_batches(
        10, question_type="comprehension", set_size=3
    ) == [3, 3, 4]


def test_resolve_question_type_auto_detects_passage_corpus() -> None:
    service = _make_service()
    directions = _passage_hit(
        "Directions (61-63): Study the following information carefully and answer "
        "the questions given below."
    )
    plain = _passage_hit("The RBI regulates commercial banks in India.")

    assert service._resolve_question_type(
        GenerateQuestionRequest(exam_id=uuid.uuid4()), [directions, directions]
    ) == "comprehension"
    assert service._resolve_question_type(
        GenerateQuestionRequest(exam_id=uuid.uuid4()), [directions, plain]
    ) == "standalone"
    # An explicit choice always wins over detection.
    assert service._resolve_question_type(
        GenerateQuestionRequest(exam_id=uuid.uuid4(), question_type="comprehension"),
        [plain, plain],
    ) == "comprehension"


def test_resolve_option_count_defaults_to_four() -> None:
    four_opt = _passage_hit(
        "1. What is 2+2?\n(a) 3 (b) 4 (c) 5 (d) 6"
    )
    five_opt = _passage_hit(
        "Directions (1-3): Study the following.\n"
        "1. Which is correct?\n(a) A (b) B (c) C (d) D (e) None of these"
    )
    assert QuestionService._resolve_option_count([four_opt, four_opt]) == 4
    assert QuestionService._resolve_option_count([five_opt]) == 5
    assert QuestionService._resolve_option_count([four_opt, five_opt]) == 5


def test_parse_question_set_reads_passage_and_questions() -> None:
    service = _make_service()
    parsed = service._parse_question_set(
        {
            "directions": "Read the passage and answer the questions that follow.",
            "passage": "Bank P holds 4 crore and Bank Q holds 6 crore in reserves.",
            "questions": [
                {
                    "stem": "Which bank holds the higher reserves?",
                    "options": ["Bank P", "Bank Q", "Both equal", "Cannot say"],
                    "correct_index": 1,
                },
                {
                    "stem": "What is the combined reserve of both banks?",
                    "options": ["8 crore", "10 crore", "12 crore", "14 crore"],
                    "correct_index": 1,
                },
                {
                    "stem": "This third question should be trimmed away.",
                    "options": ["A1", "B1", "C1", "D1"],
                    "correct_index": 0,
                },
            ],
        },
        request=GenerateQuestionRequest(exam_id=uuid.uuid4()),
        default_topic="reserves",
        expected=2,
    )
    assert parsed is not None
    assert parsed.passage.startswith("Bank P")
    assert len(parsed.questions) == 2
    assert len(parsed.questions[0].options) == 4


def test_parse_question_set_requires_passage() -> None:
    service = _make_service()
    parsed = service._parse_question_set(
        {
            "questions": [
                {
                    "stem": "Which bank holds the higher reserves?",
                    "options": ["Bank P", "Bank Q", "Both", "Neither"],
                    "correct_index": 1,
                }
            ]
        },
        request=GenerateQuestionRequest(exam_id=uuid.uuid4()),
        default_topic="reserves",
        expected=1,
    )
    assert parsed is None


@pytest.mark.asyncio
async def test_generate_comprehension_groups_questions_into_a_set() -> None:
    service = _make_service()
    exam_id = uuid.uuid4()
    service.exams.get_by_id = AsyncMock(
        return_value=Exam(id=exam_id, code="IBPS_PO", name="IBPS PO")
    )
    service.chunks.sample_for_exam = AsyncMock(
        return_value=[
            DocumentChunk(
                id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                page_number=1,
                chunk_index=0,
                content="Bus P travelled 7 km south and Bus Q travelled 6 km east.",
                summary=None,
                extra_metadata={},
            )
        ]
    )
    service.llm.generate_json = AsyncMock(
        return_value={
            "directions": "Read the passage and answer the questions that follow.",
            "passage": "Bus P travelled 7 km south. Bus Q travelled 6 km east.",
            "questions": [
                {
                    "stem": "How far south did Bus P travel?",
                    "options": ["5 km", "7 km", "8 km", "9 km"],
                    "correct_index": 1,
                },
                {
                    "stem": "In which direction did Bus Q move from the depot?",
                    "options": ["North", "East", "South", "West"],
                    "correct_index": 1,
                },
                {
                    "stem": "What is the total distance covered by both buses?",
                    "options": ["11 km", "13 km", "14 km", "15 km"],
                    "correct_index": 1,
                },
            ],
        }
    )

    async def _create(row: Question) -> Question:
        row.created_at = datetime.now(timezone.utc)
        return row

    service.questions.create = AsyncMock(side_effect=_create)

    saved, _, _, question_type = await service.generate(
        GenerateQuestionRequest(
            exam_id=exam_id,
            count=3,
            set_size=3,
            question_type="comprehension",
        )
    )

    assert question_type == "comprehension"
    assert len(saved) == 3
    # One LLM call produced the whole set.
    assert service.llm.generate_json.await_count == 1
    set_ids = {row.set_id for row in saved}
    assert len(set_ids) == 1 and None not in set_ids
    assert [row.set_index for row in saved] == [0, 1, 2]
    assert all(row.passage.startswith("Bus P travelled") for row in saved)
    assert all(row.question_type == "comprehension" for row in saved)
    assert all(len(row.options) == 4 for row in saved)


@pytest.mark.asyncio
async def test_generate_comprehension_retries_when_set_duplicates_existing() -> None:
    service = _make_service()
    exam_id = uuid.uuid4()
    service.questions.list_stems = AsyncMock(
        return_value=[
            "How far south did Bus P travel?",
            "In which direction did Bus Q move from the depot?",
        ]
    )
    service.exams.get_by_id = AsyncMock(
        return_value=Exam(id=exam_id, code="IBPS_PO", name="IBPS PO")
    )
    service.chunks.sample_for_exam = AsyncMock(
        return_value=[
            DocumentChunk(
                id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                page_number=1,
                chunk_index=0,
                content="Bus P travelled 7 km south and Bus Q travelled 6 km east.",
                summary=None,
                extra_metadata={},
            )
        ]
    )
    duplicate_set = {
        "directions": "Read the passage and answer the questions that follow.",
        "passage": "Bus P travelled 7 km south. Bus Q travelled 6 km east.",
        "questions": [
            {
                "stem": "How far south did Bus P travel?",
                "options": ["5 km", "7 km", "8 km", "9 km"],
                "correct_index": 1,
            },
            {
                "stem": "In which direction did Bus Q move from the depot?",
                "options": ["North", "East", "South", "West"],
                "correct_index": 1,
            },
        ],
    }
    fresh_set = {
        "directions": "Read the passage and answer the questions that follow.",
        "passage": "Bus R stopped twice before reaching the final terminal point.",
        "questions": [
            {
                "stem": "How many stops did Bus R make before the terminal?",
                "options": ["One", "Two", "Three", "Four"],
                "correct_index": 1,
            },
            {
                "stem": "Which vehicle reached the final terminal point?",
                "options": ["Bus P", "Bus Q", "Bus R", "Bus S"],
                "correct_index": 2,
            },
        ],
    }
    service.llm.generate_json = AsyncMock(side_effect=[duplicate_set, fresh_set])

    async def _create(row: Question) -> Question:
        row.created_at = datetime.now(timezone.utc)
        return row

    service.questions.create = AsyncMock(side_effect=_create)

    saved, _, _, _ = await service.generate(
        GenerateQuestionRequest(
            exam_id=exam_id,
            count=2,
            set_size=2,
            question_type="comprehension",
        )
    )

    assert service.llm.generate_json.await_count == 2
    assert len(saved) == 2
    assert all("Bus R" in row.passage for row in saved)


def test_is_duplicate_stem_detects_paraphrase() -> None:
    seen = {
        QuestionService._normalize_stem(
            "What is the primary function of RBI in India?"
        )
    }
    assert QuestionService._is_duplicate_stem(
        "What is the primary function of RBI in India?",
        seen,
    )
    assert QuestionService._is_duplicate_stem(
        "What is the primary function of the RBI in India?",
        seen,
    )
    assert QuestionService._is_duplicate_stem(
        "Primary function of RBI in India?",
        seen,
    )
    assert not QuestionService._is_duplicate_stem(
        "Which body issues currency notes in India?",
        seen,
    )


def test_extract_context_stems_from_qbank_chunk() -> None:
    hits = [
        SearchHit(
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            page_number=1,
            chunk_index=0,
            content=(
                "1. What is the capital of India?\n"
                "(a) Mumbai (b) Delhi\n"
                "2. Who is the banking regulator?\n"
            ),
            summary=None,
            metadata={},
            score=0.5,
        )
    ]
    stems = QuestionService._extract_context_stems(hits)
    assert any("capital of India" in s for s in stems)
    assert any("banking regulator" in s for s in stems)


def test_parse_mcqs_accepts_flat_object() -> None:
    service = _make_service()
    parsed = service._parse_mcqs(
        {
            "stem": "Who regulates banks?",
            "options": ["SEBI", "RBI", "IRDAI", "NABARD"],
            "correct_index": 1,
        },
        request=GenerateQuestionRequest(exam_id=uuid.uuid4()),
        default_topic="full_syllabus",
    )
    assert len(parsed) == 1
    assert parsed[0].correct_index == 1


def test_parse_mcqs_skips_incomplete_payload() -> None:
    service = _make_service()
    parsed = service._parse_mcqs(
        {"topic": "full_syllabus", "correct_index": 0},
        request=GenerateQuestionRequest(exam_id=uuid.uuid4()),
        default_topic="full_syllabus",
    )
    assert parsed == []

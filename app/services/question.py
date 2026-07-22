"""Question generation service — hybrid search RAG + LLM MCQs + persistence."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ProviderError, ValidationError
from app.core.logging import get_logger
from app.models.enums import SearchMode
from app.models.question import Question
from app.providers.llm.base import LLMProvider
from app.providers.llm.prompts import QUESTION_EXAMPLE_JSON, QUESTION_SYSTEM_PROMPT
from app.repositories.exam import ExamRepository
from app.repositories.question import QuestionRepository
from app.schemas.question import GeneratedMCQ, GenerateQuestionRequest
from app.schemas.search import SearchHit, SearchQuery
from app.search.service import SearchService

logger = get_logger(__name__)

_CONTEXT_CHUNK_CHARS = 800
_CONTEXT_MAX_CHUNKS = 5
_QUESTION_MAX_TOKENS = 900


class QuestionService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        llm: LLMProvider,
        search: SearchService,
    ) -> None:
        self.session = session
        self.llm = llm
        self.search = search
        self.exams = ExamRepository(session)
        self.questions = QuestionRepository(session)

    async def generate(self, request: GenerateQuestionRequest) -> tuple[list[Question], int]:
        exam = await self.exams.get_by_id(request.exam_id)
        if not exam:
            raise NotFoundError(f"Exam {request.exam_id} not found")

        search_resp = await self.search.search(
            SearchQuery(
                q=request.topic,
                mode=SearchMode.HYBRID,
                exam_id=request.exam_id,
                document_id=request.document_id,
                limit=_CONTEXT_MAX_CHUNKS,
            )
        )
        if not search_resp.items:
            raise ValidationError(
                "No knowledge-base chunks found for this exam/topic. "
                "Upload and process documents first."
            )

        context = self._build_context(search_resp.items)
        chunk_ids = [hit.chunk_id for hit in search_resp.items]
        raw = await self._call_llm(request, exam_code=exam.code, context=context)
        parsed = self._parse_mcqs(raw, request=request)
        if not parsed:
            raise ProviderError("LLM produced no valid MCQs")

        rows: list[Question] = []
        for mcq in parsed[: request.count]:
            rows.append(
                Question(
                    id=uuid.uuid4(),
                    exam_id=request.exam_id,
                    subject_id=None,
                    stem=mcq.stem,
                    options=mcq.options,
                    correct_index=mcq.correct_index,
                    explanation=mcq.explanation,
                    subject=mcq.subject or (request.subject or ""),
                    topic=mcq.topic or request.topic,
                    difficulty=mcq.difficulty,
                    source_chunk_ids=[str(cid) for cid in chunk_ids],
                    document_id=request.document_id,
                    extra_metadata={"exam_code": exam.code},
                )
            )

        saved = await self.questions.bulk_create(rows)
        logger.info(
            "questions_generated",
            exam_id=str(request.exam_id),
            topic=request.topic,
            count=len(saved),
            context_used=len(chunk_ids),
        )
        return saved, len(chunk_ids)

    async def get(self, question_id: uuid.UUID) -> Question:
        question = await self.questions.get_by_id(question_id)
        if not question:
            raise NotFoundError(f"Question {question_id} not found")
        return question

    async def list(
        self,
        *,
        exam_id: uuid.UUID | None = None,
        difficulty: str | None = None,
        topic: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Question], int]:
        return await self.questions.list(
            exam_id=exam_id,
            difficulty=difficulty,
            topic=topic,
            limit=limit,
            offset=offset,
        )

    def _build_context(self, hits: list[SearchHit]) -> str:
        parts: list[str] = []
        for i, hit in enumerate(hits, start=1):
            body = (hit.summary or hit.content or "").strip()
            body = body[:_CONTEXT_CHUNK_CHARS]
            parts.append(f"[Chunk {i} id={hit.chunk_id}]\n{body}")
        return "\n\n".join(parts)

    async def _call_llm(
        self,
        request: GenerateQuestionRequest,
        *,
        exam_code: str,
        context: str,
    ) -> dict[str, Any]:
        hints = [
            f"Exam: {exam_code}",
            f"Topic: {request.topic}",
            f"Count: {request.count}",
        ]
        if request.subject:
            hints.append(f"Subject: {request.subject}")
        if request.difficulty:
            hints.append(f"Difficulty: {request.difficulty}")
        user_prompt = (
            f"{' | '.join(hints)}\n\n"
            f"Context excerpts:\n{context}\n\n"
            f"Generate {request.count} MCQ(s) as JSON."
        )
        # OpenAI/Ollama provider accepts max_tokens; base interface includes it
        return await self.llm.generate_json(
            user_prompt,
            system=QUESTION_SYSTEM_PROMPT,
            schema_hint=QUESTION_EXAMPLE_JSON,
            max_tokens=_QUESTION_MAX_TOKENS,
        )

    def _parse_mcqs(
        self,
        raw: dict[str, Any],
        *,
        request: GenerateQuestionRequest,
    ) -> list[GeneratedMCQ]:
        items_raw: list[Any]
        if isinstance(raw.get("questions"), list):
            items_raw = raw["questions"]
        elif "stem" in raw and "options" in raw:
            items_raw = [raw]
        else:
            items_raw = []

        valid: list[GeneratedMCQ] = []
        for item in items_raw:
            if not isinstance(item, dict):
                continue
            if request.difficulty and not item.get("difficulty"):
                item = {**item, "difficulty": request.difficulty}
            if request.subject and not item.get("subject"):
                item = {**item, "subject": request.subject}
            if not item.get("topic"):
                item = {**item, "topic": request.topic}
            try:
                valid.append(GeneratedMCQ.model_validate(item))
            except Exception as exc:
                logger.warning("mcq_item_skipped", error=str(exc))
        return valid

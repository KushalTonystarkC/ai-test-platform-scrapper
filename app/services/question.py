"""Question generation service — hybrid search RAG + LLM MCQs + persistence."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ProviderError, ValidationError
from app.core.logging import get_logger
from app.models.document import DocumentChunk
from app.models.enums import SearchMode
from app.models.question import Question
from app.providers.llm.base import LLMProvider
from app.providers.llm.prompts import QUESTION_EXAMPLE_JSON, QUESTION_SYSTEM_PROMPT
from app.repositories.document import DocumentChunkRepository
from app.repositories.exam import ExamRepository
from app.repositories.question import QuestionRepository
from app.schemas.question import GeneratedMCQ, GenerateQuestionRequest
from app.schemas.search import SearchHit, SearchQuery
from app.search.service import SearchService

logger = get_logger(__name__)

# Keep tiny for CPU Ollama — large prompts cause timeouts
_CONTEXT_CHUNK_CHARS = 350
_TOPIC_CONTEXT_CHUNKS = 3
_SYLLABUS_CONTEXT_CHUNKS = 6
_QUESTION_MAX_TOKENS = 450
_FULL_SYLLABUS_TOPIC = "full_syllabus"
_MAX_ATTEMPTS_PER_QUESTION = 3

GenerationMode = Literal["topic", "full_syllabus"]


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
        self.chunks = DocumentChunkRepository(session)

    async def generate(
        self, request: GenerateQuestionRequest
    ) -> tuple[list[Question], int, GenerationMode]:
        exam = await self.exams.get_by_id(request.exam_id)
        if not exam:
            raise NotFoundError(f"Exam {request.exam_id} not found")

        mode: GenerationMode = "topic" if request.topic else "full_syllabus"
        hits = await self._resolve_context(request, mode=mode)
        if not hits:
            raise ValidationError(
                "No knowledge-base chunks found for this exam. "
                "Upload and process documents first."
            )

        chunk_ids = [hit.chunk_id for hit in hits]
        default_topic = request.topic or _FULL_SYLLABUS_TOPIC

        # One MCQ per slot with retries — local models often fail intermittently
        parsed: list[GeneratedMCQ] = []
        last_error: Exception | None = None
        for i in range(request.count):
            # Rotate context window so multi-question runs stay diverse
            window = self._context_window(hits, i)
            context = self._build_context(window)
            mcq: GeneratedMCQ | None = None
            for attempt in range(1, _MAX_ATTEMPTS_PER_QUESTION + 1):
                try:
                    raw = await self._call_llm(
                        request,
                        exam_code=exam.code,
                        context=context,
                        mode=mode,
                        default_topic=default_topic,
                        index=i + 1,
                    )
                    batch = self._parse_mcqs(
                        raw, request=request, default_topic=default_topic
                    )
                    if batch:
                        mcq = batch[0]
                        break
                    last_error = ProviderError("LLM produced no valid MCQ")
                except Exception as exc:
                    last_error = exc
                    logger.warning(
                        "question_llm_attempt_failed",
                        index=i + 1,
                        attempt=attempt,
                        error=str(exc),
                    )
            if mcq is not None:
                parsed.append(mcq)
            else:
                logger.warning(
                    "question_slot_exhausted",
                    index=i + 1,
                    error=str(last_error),
                )

        if not parsed:
            raise ProviderError(
                f"LLM produced no valid MCQs: {last_error}"
            ) from last_error

        rows: list[Question] = []
        for mcq in parsed:
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
                    topic=mcq.topic or default_topic,
                    difficulty=mcq.difficulty,
                    source_chunk_ids=[str(cid) for cid in chunk_ids],
                    document_id=request.document_id,
                    extra_metadata={"exam_code": exam.code, "generation_mode": mode},
                )
            )

        saved = await self.questions.bulk_create(rows)
        logger.info(
            "questions_generated",
            exam_id=str(request.exam_id),
            topic=default_topic,
            mode=mode,
            requested=request.count,
            count=len(saved),
            context_used=len(chunk_ids),
        )
        return saved, len(chunk_ids), mode

    def _context_window(self, hits: list[SearchHit], index: int) -> list[SearchHit]:
        """Pick a small rotating subset of hits for question #index."""
        if len(hits) <= 2:
            return hits
        start = index % len(hits)
        ordered = hits[start:] + hits[:start]
        return ordered[:2]
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

    async def _resolve_context(
        self,
        request: GenerateQuestionRequest,
        *,
        mode: GenerationMode,
    ) -> list[SearchHit]:
        if mode == "topic":
            assert request.topic is not None
            search_resp = await self.search.search(
                SearchQuery(
                    q=request.topic,
                    mode=SearchMode.HYBRID,
                    exam_id=request.exam_id,
                    document_id=request.document_id,
                    limit=_TOPIC_CONTEXT_CHUNKS,
                )
            )
            return search_resp.items

        chunks = await self.chunks.sample_for_exam(
            request.exam_id,
            document_id=request.document_id,
            limit=_SYLLABUS_CONTEXT_CHUNKS,
        )
        return [self._chunk_to_hit(c) for c in chunks]

    @staticmethod
    def _chunk_to_hit(chunk: DocumentChunk) -> SearchHit:
        return SearchHit(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            page_number=chunk.page_number,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            summary=chunk.summary,
            metadata=chunk.extra_metadata or {},
            score=0.0,
        )

    def _build_context(self, hits: list[SearchHit]) -> str:
        parts: list[str] = []
        for i, hit in enumerate(hits, start=1):
            body = (hit.summary or hit.content or "").strip()
            body = body[:_CONTEXT_CHUNK_CHARS]
            parts.append(f"[{i}] {body}")
        return "\n".join(parts)

    async def _call_llm(
        self,
        request: GenerateQuestionRequest,
        *,
        exam_code: str,
        context: str,
        mode: GenerationMode,
        default_topic: str,
        index: int,
    ) -> dict[str, Any]:
        hints = [f"Exam:{exam_code}", f"Mode:{mode}", f"Q#:{index}"]
        if mode == "topic":
            hints.append(f"Topic:{request.topic}")
        else:
            hints.append("Cover a different syllabus area than prior questions.")
        if request.subject:
            hints.append(f"Subject:{request.subject}")
        if request.difficulty:
            hints.append(f"Difficulty:{request.difficulty}")
        user_prompt = (
            f"{' | '.join(hints)}\n"
            f"Context:\n{context}\n"
            f"Generate exactly 1 MCQ JSON. topic hint: {default_topic}"
        )
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
        default_topic: str,
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
                item = {**item, "topic": default_topic}
            try:
                valid.append(GeneratedMCQ.model_validate(item))
            except Exception as exc:
                logger.warning("mcq_item_skipped", error=str(exc))
        return valid

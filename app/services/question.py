"""Question generation service — hybrid search RAG + LLM MCQs + persistence."""

from __future__ import annotations

import random
import re
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
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
from app.schemas.question import GeneratedMCQ, GenerateQuestionRequest, QuestionRead
from app.schemas.search import SearchHit, SearchQuery
from app.search.service import SearchService

logger = get_logger(__name__)

# Keep tiny for CPU Ollama — large prompts cause timeouts
_CONTEXT_CHUNK_CHARS = 350
_TOPIC_CONTEXT_CHUNKS = 5
_SYLLABUS_CONTEXT_CHUNKS = 8
_QUESTION_MAX_TOKENS = 650
_FULL_SYLLABUS_TOPIC = "full_syllabus"
_MAX_ATTEMPTS_PER_QUESTION = 5
_STEM_OVERLAP_DUP_THRESHOLD = 0.72

_ANGLE_HINTS = (
    "Ask about a definition or primary role.",
    "Ask about a concrete function, power, or duty mentioned in the context.",
    "Ask about a comparison, exception, or limitation from the context.",
    "Ask about a number, year, body, act, or named entity in the context.",
    "Ask about a cause, effect, or purpose stated in the context.",
)

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
        self._settings = get_settings()

    async def generate(
        self, request: GenerateQuestionRequest
    ) -> tuple[list[Question], int, GenerationMode]:
        items: list[Question] = []
        context_used = 0
        mode: GenerationMode = "topic" if request.topic else "full_syllabus"
        async for event in self.generate_events(request, persist=True):
            if event["event"] == "started":
                context_used = int(event["context_used"])
                mode = event["mode"]  # type: ignore[assignment]
            elif event["event"] == "question":
                items.append(event["question"])  # type: ignore[arg-type]
            elif event["event"] == "error":
                raise ProviderError(str(event["error"]))
        if not items:
            raise ProviderError("LLM produced no valid MCQs")
        return items, context_used, mode

    async def generate_events(
        self,
        request: GenerateQuestionRequest,
        *,
        persist: bool = True,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield progress events while generating MCQs (for SSE / batch callers)."""
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
        yield {
            "event": "started",
            "exam_id": str(request.exam_id),
            "topic": request.topic,
            "mode": mode,
            "requested_count": request.count,
            "context_used": len(chunk_ids),
        }

        parsed: list[GeneratedMCQ] = []
        saved_rows: list[Question] = []
        seen_stems: set[str] = set()
        last_error: Exception | None = None
        base_seed = random.randint(1, 1_000_000)

        for i in range(request.count):
            yield {
                "event": "slot_started",
                "index": i + 1,
                "total": request.count,
            }
            mcq: GeneratedMCQ | None = None
            retry_feedback: str | None = None
            for attempt in range(1, _MAX_ATTEMPTS_PER_QUESTION + 1):
                window = self._context_window(hits, i, attempt=attempt)
                context = self._build_context(window)
                try:
                    raw = await self._call_llm(
                        request,
                        exam_code=exam.code,
                        context=context,
                        mode=mode,
                        default_topic=default_topic,
                        index=i + 1,
                        prior_stems=[m.stem for m in parsed],
                        retry_feedback=retry_feedback,
                        seed=base_seed + i * _MAX_ATTEMPTS_PER_QUESTION + attempt,
                        temperature=min(
                            2.0,
                            self._settings.llm_question_temperature
                            + min(0.25, 0.05 * (attempt - 1)),
                        ),
                    )
                    batch = self._parse_mcqs(
                        raw, request=request, default_topic=default_topic
                    )
                    candidate = batch[0] if batch else None
                    if candidate is None:
                        last_error = ProviderError("LLM produced no valid MCQ")
                        retry_feedback = self._generation_feedback(raw)
                        yield {
                            "event": "attempt_failed",
                            "index": i + 1,
                            "attempt": attempt,
                            "error": retry_feedback,
                        }
                        continue
                    if self._is_duplicate_stem(candidate.stem, seen_stems):
                        last_error = ProviderError("LLM produced a duplicate MCQ")
                        retry_feedback = (
                            "The previous question duplicated an earlier stem. "
                            "Use a different fact from the context and a new wording."
                        )
                        logger.info(
                            "question_duplicate_skipped",
                            index=i + 1,
                            attempt=attempt,
                            stem=candidate.stem,
                        )
                        yield {
                            "event": "attempt_failed",
                            "index": i + 1,
                            "attempt": attempt,
                            "error": "duplicate_stem",
                            "stem": candidate.stem,
                        }
                        continue
                    mcq = candidate
                    break
                except Exception as exc:
                    last_error = exc
                    retry_feedback = (
                        "Previous attempt failed. Return one complete JSON object "
                        "with stem and exactly 4 options."
                    )
                    logger.warning(
                        "question_llm_attempt_failed",
                        index=i + 1,
                        attempt=attempt,
                        error=str(exc),
                    )
                    yield {
                        "event": "attempt_failed",
                        "index": i + 1,
                        "attempt": attempt,
                        "error": str(exc),
                    }

            if mcq is None:
                logger.warning(
                    "question_slot_exhausted",
                    index=i + 1,
                    error=str(last_error),
                )
                yield {
                    "event": "slot_exhausted",
                    "index": i + 1,
                    "error": str(last_error) if last_error else "unknown",
                }
                continue

            parsed.append(mcq)
            seen_stems.add(self._normalize_stem(mcq.stem))
            row = Question(
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
            if persist:
                row = await self.questions.create(row)
            else:
                # Tests / dry-runs still need a timestamp for QuestionRead.
                row.created_at = datetime.now(timezone.utc)
            saved_rows.append(row)
            yield {
                "event": "question",
                "index": i + 1,
                "question": row,
                "item": QuestionRead.model_validate(row).model_dump(mode="json"),
            }

        if not saved_rows:
            yield {
                "event": "error",
                "error": f"LLM produced no valid MCQs: {last_error}",
            }
            return

        logger.info(
            "questions_generated",
            exam_id=str(request.exam_id),
            topic=default_topic,
            mode=mode,
            requested=request.count,
            count=len(saved_rows),
            context_used=len(chunk_ids),
        )
        yield {
            "event": "done",
            "exam_id": str(request.exam_id),
            "topic": request.topic,
            "mode": mode,
            "requested_count": request.count,
            "generated_count": len(saved_rows),
            "context_used": len(chunk_ids),
        }

    def _context_window(
        self,
        hits: list[SearchHit],
        index: int,
        *,
        attempt: int = 1,
    ) -> list[SearchHit]:
        """Pick a rotating subset of hits; shift further on retries for diversity."""
        if not hits:
            return []
        if len(hits) == 1:
            return hits
        start = (index + (attempt - 1)) % len(hits)
        ordered = hits[start:] + hits[:start]
        # Prefer two distinct chunks; on later attempts take a wider window.
        width = 2 if attempt < 3 else min(3, len(hits))
        return ordered[:width]

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

    async def delete(self, question_id: uuid.UUID) -> None:
        deleted = await self.questions.delete_by_id(question_id)
        if not deleted:
            raise NotFoundError(f"Question {question_id} not found")

    async def clear(
        self,
        *,
        exam_id: uuid.UUID | None = None,
    ) -> int:
        return await self.questions.delete_all(exam_id=exam_id)

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
        prior_stems: list[str] | None = None,
        retry_feedback: str | None = None,
        seed: int | None = None,
        temperature: float | None = None,
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
        angle = _ANGLE_HINTS[(index - 1) % len(_ANGLE_HINTS)]
        user_prompt = (
            f"{' | '.join(hints)}\n"
            f"Angle: {angle}\n"
            f"Context:\n{context}\n"
            f"Generate exactly 1 MCQ JSON. topic hint: {default_topic}"
        )
        # Steer the model away from questions it already produced this run.
        avoid = self._format_avoid_block(prior_stems)
        if avoid:
            user_prompt = f"{user_prompt}\n{avoid}"
        if retry_feedback:
            user_prompt = f"{user_prompt}\nCORRECT THE PREVIOUS ERROR: {retry_feedback}"
        return await self.llm.generate_json(
            user_prompt,
            system=QUESTION_SYSTEM_PROMPT,
            schema_hint=QUESTION_EXAMPLE_JSON,
            max_tokens=_QUESTION_MAX_TOKENS,
            temperature=(
                temperature
                if temperature is not None
                else self._settings.llm_question_temperature
            ),
            seed=seed,
        )

    @staticmethod
    def _format_avoid_block(prior_stems: list[str] | None) -> str:
        if not prior_stems:
            return ""
        # Cap to the most recent few to keep the prompt small for local models.
        recent = prior_stems[-5:]
        listed = "\n".join(f"- {stem}" for stem in recent)
        return (
            "Do NOT repeat or paraphrase any of these already-asked questions. "
            "Ask about a different fact/concept:\n"
            f"{listed}"
        )

    @staticmethod
    def _normalize_stem(stem: str) -> str:
        """Normalize a stem for duplicate detection (case/punctuation/space)."""
        return re.sub(r"[^a-z0-9]+", " ", stem.lower()).strip()

    @classmethod
    def _is_duplicate_stem(cls, stem: str, seen: set[str]) -> bool:
        """Exact normalized match or high token-overlap paraphrase."""
        normalized = cls._normalize_stem(stem)
        if not normalized:
            return True
        if normalized in seen:
            return True
        tokens = set(normalized.split())
        if not tokens:
            return True
        for prior in seen:
            prior_tokens = set(prior.split())
            if not prior_tokens:
                continue
            overlap = len(tokens & prior_tokens) / max(len(tokens), len(prior_tokens))
            if overlap >= _STEM_OVERLAP_DUP_THRESHOLD:
                return True
        return False

    @staticmethod
    def _generation_feedback(raw: dict[str, Any]) -> str:
        """Give the next retry a compact explanation of malformed output."""
        questions = raw.get("questions")
        item = questions[0] if isinstance(questions, list) and questions else raw
        if not isinstance(item, dict):
            return (
                "Return one JSON object with keys stem, options (exactly 4 strings), "
                "correct_index, explanation, subject, topic, difficulty."
            )
        missing = [k for k in ("stem", "options") if not item.get(k)]
        if missing:
            return (
                f"Previous JSON was missing required fields: {', '.join(missing)}. "
                "Include stem and options with exactly 4 distinct non-empty strings."
            )
        options = item.get("options")
        if isinstance(options, list):
            return (
                f"The previous options array had {len(options)} items. "
                "Return exactly 4 distinct options."
            )
        return "Return options as a JSON array containing exactly 4 strings."

    def _parse_mcqs(
        self,
        raw: dict[str, Any],
        *,
        request: GenerateQuestionRequest,
        default_topic: str,
    ) -> list[GeneratedMCQ]:
        items_raw: list[Any]
        if isinstance(raw.get("questions"), list) and raw["questions"]:
            # Small models sometimes emit multiple partial items — only trust the first.
            items_raw = [raw["questions"][0]]
        elif "stem" in raw or "question" in raw:
            items_raw = [raw]
        else:
            items_raw = []

        valid: list[GeneratedMCQ] = []
        for item in items_raw:
            if not isinstance(item, dict):
                continue
            # Skip obviously incomplete payloads before Pydantic (clearer logs/feedback)
            if not (item.get("stem") or item.get("question") or item.get("question_text")):
                logger.warning("mcq_item_skipped", error="missing stem")
                continue
            if item.get("options") is None and item.get("choices") is None:
                logger.warning("mcq_item_skipped", error="missing options")
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

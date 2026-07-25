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
from app.providers.llm.prompts import (
    COMPREHENSION_EXAMPLE_JSON,
    QUESTION_EXAMPLE_JSON,
    comprehension_system_prompt,
    question_system_prompt,
)
from app.repositories.document import DocumentChunkRepository
from app.repositories.exam import ExamRepository
from app.repositories.question import QuestionRepository
from app.schemas.question import (
    GeneratedMCQ,
    GeneratedQuestionSet,
    GenerateQuestionRequest,
    QuestionRead,
)
from app.schemas.search import SearchHit, SearchQuery
from app.search.service import SearchService

logger = get_logger(__name__)

# Keep tiny for CPU Ollama — large prompts cause timeouts
_CONTEXT_CHUNK_CHARS = 350
_TOPIC_CONTEXT_CHUNKS = 5
_SYLLABUS_CONTEXT_CHUNKS = 8
_MAX_CONTEXT_POOL = 24
_QUESTION_MAX_TOKENS = 650
_FULL_SYLLABUS_TOPIC = "full_syllabus"
_MAX_ATTEMPTS_PER_QUESTION = 5
# A shared passage needs more source material and more room to come back.
_COMPREHENSION_CONTEXT_CHARS = 900
_COMPREHENSION_CONTEXT_WIDTH = 3
_COMPREHENSION_MAX_TOKENS = 1600
_MIN_SET_QUESTIONS = 2
# "auto" only switches to comprehension when the corpus really looks passage-based.
_MIN_PASSAGE_HITS_FOR_AUTO = 2
# Jaccard on content tokens; containment catches short/long paraphrases.
_STEM_JACCARD_DUP_THRESHOLD = 0.55
_STEM_CONTAINMENT_DUP_THRESHOLD = 0.72
_AVOID_BLOCK_LIMIT = 12
_EXISTING_STEMS_LIMIT = 500
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "of",
        "in",
        "on",
        "at",
        "to",
        "for",
        "and",
        "or",
        "is",
        "are",
        "was",
        "were",
        "be",
        "by",
        "with",
        "from",
        "as",
        "that",
        "this",
        "these",
        "those",
        "which",
        "what",
        "who",
        "whom",
        "whose",
        "when",
        "where",
        "why",
        "how",
        "does",
        "do",
        "did",
        "can",
        "could",
        "should",
        "would",
        "will",
        "may",
        "might",
        "must",
        "not",
        "no",
        "its",
        "it",
        "their",
        "there",
        "than",
        "into",
        "about",
        "following",
        "according",
        "among",
        "between",
        "under",
        "over",
        "also",
        "only",
        "main",
        "primary",
        "major",
    }
)
# Lines that look like existing MCQ stems inside source chunks (PYQ / Q-bank PDFs).
_CONTEXT_QUESTION_RE = re.compile(
    r"(?im)^\s*(?:\d{1,3}[\).\:\-]\s*|[qQ](?:uestion)?\s*\d{0,3}[\).\:\-]?\s*)?"
    r"(.{12,220}\?)\s*$"
)
# Shared-stimulus markers: "Directions (61-63):", caselets, puzzles, passages.
# Kept exam-agnostic — works for banking, SSC, railway, and similar papers.
_CONTEXT_SET_RE = re.compile(
    r"(?i)\b(?:directions?\s*\(|directions?\s*\d{1,3}\s*[-–]"
    r"|study the following (?:information|passage|table|graph|data)"
    r"|read the following (?:passage|paragraph|information)"
    r"|answer the questions? (?:that follow|given )?below"
    r"|based on the (?:passage|information|paragraph) given"
    r"|following (?:passage|caselet|paragraph)\b"
    r"|comprehension\b)"
)
# Prefer 5 choices only when the source paper clearly uses them.
_FIVE_OPTION_RE = re.compile(
    r"(?is)\([eE]\)"
    r"|\bnone of (?:these|the above)\b"
    r"|\([aA]\).{0,200}\([bB]\).{0,200}\([cC]\).{0,200}\([dD]\).{0,200}\([eE]\)"
)

_ANGLE_HINTS = (
    "Ask about a definition or primary role.",
    "Ask about a concrete function, power, or duty mentioned in the context.",
    "Ask about a comparison, exception, or limitation from the context.",
    "Ask about a number, year, body, act, or named entity in the context.",
    "Ask about a cause, effect, or purpose stated in the context.",
)
_SET_ANGLE_HINT = (
    "Spread the questions across different facts of the passage: one on a directly "
    "stated detail, one requiring a comparison or inference, and one on a number, "
    "order, or named entity."
)

GenerationMode = Literal["topic", "full_syllabus"]
QuestionType = Literal["standalone", "comprehension"]


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
    ) -> tuple[list[Question], int, GenerationMode, QuestionType]:
        items: list[Question] = []
        context_used = 0
        mode: GenerationMode = "topic" if request.topic else "full_syllabus"
        question_type: QuestionType = "standalone"
        async for event in self.generate_events(request, persist=True):
            if event["event"] == "started":
                context_used = int(event["context_used"])
                mode = event["mode"]  # type: ignore[assignment]
                question_type = event["question_type"]  # type: ignore[assignment]
            elif event["event"] == "question":
                items.append(event["question"])  # type: ignore[arg-type]
            elif event["event"] == "error":
                raise ProviderError(str(event["error"]))
        if not items:
            raise ProviderError("LLM produced no valid MCQs")
        return items, context_used, mode, question_type

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

        # Seed against already-saved questions so re-runs don't regenerate the same MCQs.
        existing_stems = await self.questions.list_stems(
            exam_id=request.exam_id,
            document_id=request.document_id,
            limit=_EXISTING_STEMS_LIMIT,
        )
        # Also treat question-like lines already present in the context (PYQ / Q-banks)
        # as taken — generation must invent new stems, not copy the source paper.
        context_stems = self._extract_context_stems(hits)
        prior_stems = list(dict.fromkeys([*existing_stems, *context_stems]))
        seen_stems = {
            self._normalize_stem(stem) for stem in prior_stems if self._normalize_stem(stem)
        }

        question_type = self._resolve_question_type(request, hits)
        option_count = self._resolve_option_count(hits)
        batch_sizes = self._plan_batches(
            request.count, question_type=question_type, set_size=request.set_size
        )

        yield {
            "event": "started",
            "exam_id": str(request.exam_id),
            "topic": request.topic,
            "mode": mode,
            "question_type": question_type,
            "option_count": option_count,
            "requested_count": request.count,
            "set_count": len(batch_sizes) if question_type == "comprehension" else 0,
            "context_used": len(chunk_ids),
            "existing_stems_blocked": len(seen_stems),
        }

        saved_rows: list[Question] = []
        seen_passages: set[str] = set()
        last_error: Exception | None = None
        base_seed = random.randint(1, 1_000_000)
        produced = 0

        for batch_no, batch_size in enumerate(batch_sizes):
            yield {
                "event": "slot_started",
                "index": produced + 1,
                "total": request.count,
                "question_type": question_type,
                "batch_size": batch_size,
            }
            if question_type == "comprehension":
                yield {
                    "event": "set_started",
                    "set_number": batch_no + 1,
                    "set_total": len(batch_sizes),
                    "size": batch_size,
                }

            batch: list[GeneratedMCQ] = []
            directions = ""
            passage = ""
            retry_feedback: str | None = None

            for attempt in range(1, _MAX_ATTEMPTS_PER_QUESTION + 1):
                # On later retries, refresh syllabus context so we escape a stuck chunk set.
                if mode == "full_syllabus" and attempt >= 3:
                    refreshed = await self._resolve_context(request, mode=mode)
                    if refreshed:
                        hits = refreshed
                        chunk_ids = [hit.chunk_id for hit in hits]
                comprehension = question_type == "comprehension"
                window = self._context_window(
                    hits,
                    batch_no,
                    attempt=attempt,
                    width=_COMPREHENSION_CONTEXT_WIDTH if comprehension else None,
                )
                context = self._build_context(
                    window,
                    max_chars=(
                        _COMPREHENSION_CONTEXT_CHARS
                        if comprehension
                        else _CONTEXT_CHUNK_CHARS
                    ),
                )
                try:
                    raw = await self._call_llm(
                        request,
                        exam_code=exam.code,
                        context=context,
                        mode=mode,
                        question_type=question_type,
                        batch_size=batch_size,
                        option_count=option_count,
                        default_topic=default_topic,
                        index=produced + 1,
                        prior_stems=prior_stems,
                        retry_feedback=retry_feedback,
                        seed=base_seed + batch_no * _MAX_ATTEMPTS_PER_QUESTION + attempt,
                        temperature=min(
                            2.0,
                            self._settings.llm_question_temperature
                            + min(0.25, 0.05 * (attempt - 1)),
                        ),
                    )
                    question_set: GeneratedQuestionSet | None = None
                    if comprehension:
                        question_set = self._parse_question_set(
                            raw,
                            request=request,
                            default_topic=default_topic,
                            expected=batch_size,
                        )
                        candidates = list(question_set.questions) if question_set else []
                    else:
                        candidates = self._parse_mcqs(
                            raw, request=request, default_topic=default_topic
                        )[:1]

                    if not candidates:
                        last_error = ProviderError("LLM produced no valid MCQ")
                        retry_feedback = self._generation_feedback(
                            raw,
                            question_type=question_type,
                            expected=batch_size,
                            option_count=option_count,
                        )
                        yield {
                            "event": "attempt_failed",
                            "index": produced + 1,
                            "attempt": attempt,
                            "error": retry_feedback,
                        }
                        continue

                    if question_set is not None and self._is_duplicate_stem(
                        question_set.passage, seen_passages
                    ):
                        last_error = ProviderError("LLM reused an earlier passage")
                        retry_feedback = (
                            "The previous passage repeated an earlier one. Build a new "
                            "passage from different facts in the context."
                        )
                        yield {
                            "event": "attempt_failed",
                            "index": produced + 1,
                            "attempt": attempt,
                            "error": "duplicate_passage",
                        }
                        continue

                    unique, duplicate = self._filter_duplicate_stems(candidates, seen_stems)
                    required = (
                        min(_MIN_SET_QUESTIONS, batch_size) if comprehension else 1
                    )
                    if len(unique) < required:
                        last_error = ProviderError("LLM produced a duplicate MCQ")
                        retry_feedback = (
                            "The previous question duplicated an existing or earlier stem. "
                            "Use a different fact from the context and completely new wording."
                        )
                        logger.info(
                            "question_duplicate_skipped",
                            index=produced + 1,
                            attempt=attempt,
                            stem=duplicate or "",
                        )
                        yield {
                            "event": "attempt_failed",
                            "index": produced + 1,
                            "attempt": attempt,
                            "error": "duplicate_stem",
                            "stem": duplicate or "",
                        }
                        continue

                    batch = unique
                    if question_set is not None:
                        directions = question_set.directions
                        passage = question_set.passage
                    break
                except Exception as exc:
                    last_error = exc
                    retry_feedback = (
                        "Previous attempt failed. Return one complete JSON object "
                        f"with stem and exactly {option_count} options."
                    )
                    logger.warning(
                        "question_llm_attempt_failed",
                        index=produced + 1,
                        attempt=attempt,
                        error=str(exc),
                    )
                    yield {
                        "event": "attempt_failed",
                        "index": produced + 1,
                        "attempt": attempt,
                        "error": str(exc),
                    }

            if not batch:
                logger.warning(
                    "question_slot_exhausted",
                    index=produced + 1,
                    error=str(last_error),
                )
                yield {
                    "event": "slot_exhausted",
                    "index": produced + 1,
                    "error": str(last_error) if last_error else "unknown",
                }
                continue

            set_id = uuid.uuid4() if question_type == "comprehension" else None
            if passage:
                seen_passages.add(self._normalize_stem(passage))

            for offset, mcq in enumerate(batch):
                produced += 1
                seen_stems.add(self._normalize_stem(mcq.stem))
                prior_stems.append(mcq.stem)
                row = Question(
                    id=uuid.uuid4(),
                    exam_id=request.exam_id,
                    subject_id=None,
                    question_type=question_type,
                    set_id=set_id,
                    set_index=offset,
                    directions=directions,
                    passage=passage,
                    stem=mcq.stem,
                    options=mcq.options,
                    correct_index=mcq.correct_index,
                    explanation=mcq.explanation,
                    subject=mcq.subject or (request.subject or ""),
                    topic=mcq.topic or default_topic,
                    difficulty=mcq.difficulty,
                    source_chunk_ids=[str(cid) for cid in chunk_ids],
                    document_id=request.document_id,
                    extra_metadata={
                        "exam_code": exam.code,
                        "generation_mode": mode,
                        "question_type": question_type,
                        "set_size": len(batch),
                        "option_count": option_count,
                    },
                )
                if persist:
                    row = await self.questions.create(row)
                else:
                    # Tests / dry-runs still need a timestamp for QuestionRead.
                    row.created_at = datetime.now(timezone.utc)
                saved_rows.append(row)
                yield {
                    "event": "question",
                    "index": produced,
                    "question": row,
                    "item": QuestionRead.model_validate(row).model_dump(mode="json"),
                }

            if set_id is not None:
                yield {
                    "event": "set_ready",
                    "set_number": batch_no + 1,
                    "set_id": str(set_id),
                    "directions": directions,
                    "passage": passage,
                    "question_count": len(batch),
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
            question_type=question_type,
            requested=request.count,
            count=len(saved_rows),
            context_used=len(chunk_ids),
        )
        yield {
            "event": "done",
            "exam_id": str(request.exam_id),
            "topic": request.topic,
            "mode": mode,
            "question_type": question_type,
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
        width: int | None = None,
    ) -> list[SearchHit]:
        """Pick a rotating, mostly non-overlapping subset of hits for diversity."""
        if not hits:
            return []
        if len(hits) == 1:
            return hits
        # Stride by 2 so consecutive slots prefer different chunk pairs.
        start = (index * 2 + (attempt - 1) * 3) % len(hits)
        ordered = hits[start:] + hits[:start]
        if width is None:
            width = 2 if attempt < 3 else 3
        return ordered[: min(width, len(hits))]

    def _resolve_question_type(
        self,
        request: GenerateQuestionRequest,
        hits: list[SearchHit],
    ) -> QuestionType:
        """Honour an explicit request, else infer from how the source material reads."""
        if request.question_type in ("standalone", "comprehension"):
            return request.question_type  # type: ignore[return-value]
        passage_like = sum(
            1
            for hit in hits
            if _CONTEXT_SET_RE.search(f"{hit.summary or ''}\n{hit.content or ''}")
        )
        return (
            "comprehension" if passage_like >= _MIN_PASSAGE_HITS_FOR_AUTO else "standalone"
        )

    @staticmethod
    def _resolve_option_count(hits: list[SearchHit]) -> int:
        """Default to 4 options; use 5 only when the source paper clearly uses them.

        Many exams (NEET, JEE, CAT, some SSC papers) use 4 choices. Banking papers
        often use 5 with \"None of these\". Infer from the uploaded material rather
        than hard-coding one exam family's format.
        """
        five_hits = 0
        for hit in hits:
            body = f"{hit.summary or ''}\n{hit.content or ''}"
            if _FIVE_OPTION_RE.search(body):
                five_hits += 1
        return 5 if five_hits >= 1 else 4

    @staticmethod
    def _plan_batches(
        count: int,
        *,
        question_type: QuestionType,
        set_size: int,
    ) -> list[int]:
        """Split the requested count into LLM calls (1 per question, or 1 per set)."""
        if question_type != "comprehension":
            return [1] * count
        sizes: list[int] = []
        remaining = count
        while remaining > 0:
            take = min(set_size, remaining)
            sizes.append(take)
            remaining -= take
        # A trailing 1-question "set" isn't worth its own passage — fold it back.
        if len(sizes) > 1 and sizes[-1] < _MIN_SET_QUESTIONS:
            tail = sizes.pop()
            sizes[-1] += tail
        return sizes

    @classmethod
    def _filter_duplicate_stems(
        cls,
        candidates: list[GeneratedMCQ],
        seen: set[str],
    ) -> tuple[list[GeneratedMCQ], str | None]:
        """Drop candidates duplicating prior stems or each other; report the first drop."""
        local_seen = set(seen)
        unique: list[GeneratedMCQ] = []
        first_duplicate: str | None = None
        for candidate in candidates:
            if cls._is_duplicate_stem(candidate.stem, local_seen):
                if first_duplicate is None:
                    first_duplicate = candidate.stem
                continue
            local_seen.add(cls._normalize_stem(candidate.stem))
            unique.append(candidate)
        return unique, first_duplicate

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

    def _context_pool_size(self, request: GenerateQuestionRequest) -> int:
        """Scale chunk pool with requested count so slots can use distinct windows."""
        return min(_MAX_CONTEXT_POOL, max(_SYLLABUS_CONTEXT_CHUNKS, request.count * 2))

    async def _resolve_context(
        self,
        request: GenerateQuestionRequest,
        *,
        mode: GenerationMode,
    ) -> list[SearchHit]:
        pool = self._context_pool_size(request)
        if mode == "topic":
            assert request.topic is not None
            search_resp = await self.search.search(
                SearchQuery(
                    q=request.topic,
                    mode=SearchMode.HYBRID,
                    exam_id=request.exam_id,
                    document_id=request.document_id,
                    limit=max(_TOPIC_CONTEXT_CHUNKS, min(pool, 12)),
                )
            )
            return search_resp.items

        chunks = await self.chunks.sample_for_exam(
            request.exam_id,
            document_id=request.document_id,
            limit=pool,
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

    def _build_context(
        self,
        hits: list[SearchHit],
        *,
        max_chars: int = _CONTEXT_CHUNK_CHARS,
    ) -> str:
        parts: list[str] = []
        for i, hit in enumerate(hits, start=1):
            # Prefer raw chunk text: LLM summaries can be wrong (esp. tiny local
            # models parroting the metadata few-shot example) and would bias MCQs.
            body = (hit.content or hit.summary or "").strip()
            parts.append(f"[{i}] {body[:max_chars]}")
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
        question_type: QuestionType = "standalone",
        batch_size: int = 1,
        option_count: int = 4,
        prior_stems: list[str] | None = None,
        retry_feedback: str | None = None,
        seed: int | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        comprehension = question_type == "comprehension"
        option_count = 5 if option_count >= 5 else 4
        hints = [
            f"Exam:{exam_code}",
            f"Mode:{mode}",
            f"Q#:{index}",
            f"Options:{option_count}",
        ]
        if mode == "topic":
            hints.append(f"Topic:{request.topic}")
        else:
            hints.append("Cover a different syllabus area than prior questions.")
        if request.subject:
            hints.append(f"Subject:{request.subject}")
        if request.difficulty:
            hints.append(f"Difficulty:{request.difficulty}")

        if comprehension:
            hints.append(f"Questions in this set: {batch_size}")
            instruction = (
                f"Generate exactly {batch_size} linked questions sharing one passage, "
                f"each with exactly {option_count} options. "
                f"Match {exam_code} style from the context. topic hint: {default_topic}"
            )
            angle = _SET_ANGLE_HINT
        else:
            instruction = (
                f"Generate exactly 1 MCQ JSON with exactly {option_count} options. "
                f"Match {exam_code} style from the context. topic hint: {default_topic}"
            )
            angle = _ANGLE_HINTS[(index - 1) % len(_ANGLE_HINTS)]

        user_prompt = (
            f"{' | '.join(hints)}\n"
            f"Angle: {angle}\n"
            f"Context:\n{context}\n"
            f"{instruction}"
        )
        # Steer the model away from questions it already produced this run.
        avoid = self._format_avoid_block(prior_stems)
        if avoid:
            user_prompt = f"{user_prompt}\n{avoid}"
        if retry_feedback:
            user_prompt = f"{user_prompt}\nCORRECT THE PREVIOUS ERROR: {retry_feedback}"

        schema_hint: dict[str, Any]
        if comprehension:
            schema_hint = {
                **COMPREHENSION_EXAMPLE_JSON,
                "questions": [
                    {
                        **COMPREHENSION_EXAMPLE_JSON["questions"][0],
                        "options": (
                            ["One", "Two", "Three", "Four", "None of these"]
                            if option_count == 5
                            else ["One", "Two", "Three", "Four"]
                        ),
                    }
                ],
            }
        else:
            schema_hint = QUESTION_EXAMPLE_JSON

        return await self.llm.generate_json(
            user_prompt,
            system=(
                comprehension_system_prompt(batch_size, option_count=option_count)
                if comprehension
                else question_system_prompt(option_count=option_count)
            ),
            schema_hint=schema_hint,
            max_tokens=(
                _COMPREHENSION_MAX_TOKENS if comprehension else _QUESTION_MAX_TOKENS
            ),
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
        # Prefer newest stems (this run + recent DB) while capping prompt size.
        recent = prior_stems[-_AVOID_BLOCK_LIMIT:]
        # If we have a large bank, also sample a few older stems for coverage.
        older: list[str] = []
        if len(prior_stems) > _AVOID_BLOCK_LIMIT:
            head = prior_stems[: -_AVOID_BLOCK_LIMIT]
            step = max(1, len(head) // 4)
            older = head[::step][:4]
        listed_stems = list(dict.fromkeys([*older, *recent]))
        listed = "\n".join(f"- {stem}" for stem in listed_stems)
        return (
            "Do NOT repeat, copy, or paraphrase any of these already-asked questions. "
            "Ask about a different fact/concept with different wording:\n"
            f"{listed}"
        )

    @staticmethod
    def _normalize_stem(stem: str) -> str:
        """Normalize a stem for duplicate detection (case/punctuation/space)."""
        return re.sub(r"[^a-z0-9]+", " ", stem.lower()).strip()

    @classmethod
    def _stem_tokens(cls, stem: str) -> set[str]:
        normalized = cls._normalize_stem(stem)
        if not normalized:
            return set()
        return {tok for tok in normalized.split() if tok not in _STOPWORDS and len(tok) > 1}

    @classmethod
    def _is_duplicate_stem(cls, stem: str, seen: set[str]) -> bool:
        """Exact normalized match, high Jaccard, or high token containment."""
        normalized = cls._normalize_stem(stem)
        if not normalized:
            return True
        if normalized in seen:
            return True
        tokens = cls._stem_tokens(stem)
        if not tokens:
            return True
        for prior in seen:
            prior_tokens = cls._stem_tokens(prior)
            if not prior_tokens:
                continue
            intersection = len(tokens & prior_tokens)
            # Ignore weak overlaps from one/two shared content words (e.g. "RBI").
            if intersection < 3:
                continue
            union = len(tokens | prior_tokens)
            if union and (intersection / union) >= _STEM_JACCARD_DUP_THRESHOLD:
                return True
            smaller = min(len(tokens), len(prior_tokens))
            if smaller and (intersection / smaller) >= _STEM_CONTAINMENT_DUP_THRESHOLD:
                return True
        return False

    @classmethod
    def _extract_context_stems(cls, hits: list[SearchHit]) -> list[str]:
        """Pull question-like lines out of chunk text so PYQ copies are blocked."""
        found: list[str] = []
        seen_norm: set[str] = set()
        for hit in hits:
            body = f"{hit.summary or ''}\n{hit.content or ''}"
            for match in _CONTEXT_QUESTION_RE.finditer(body):
                stem = match.group(1).strip()
                norm = cls._normalize_stem(stem)
                if not norm or norm in seen_norm:
                    continue
                seen_norm.add(norm)
                found.append(stem)
        return found

    @staticmethod
    def _generation_feedback(
        raw: dict[str, Any],
        *,
        question_type: QuestionType = "standalone",
        expected: int = 1,
        option_count: int = 4,
    ) -> str:
        """Give the next retry a compact explanation of malformed output."""
        option_count = 5 if option_count >= 5 else 4
        questions = raw.get("questions")
        if question_type == "comprehension":
            if not isinstance(questions, list) or not questions:
                return (
                    "Previous JSON had no usable questions array. Return keys "
                    f"directions, passage, and questions with exactly {expected} items."
                )
            if not str(raw.get("passage") or "").strip():
                return (
                    "Previous JSON was missing the shared passage. Include a 60-150 word "
                    "passage that contains every fact the questions rely on."
                )
            return (
                f"Previous JSON had {len(questions)} question(s) but {expected} are "
                f"required, each with exactly {option_count} distinct options and "
                f"correct_index 0-{option_count - 1}."
            )
        item = questions[0] if isinstance(questions, list) and questions else raw
        if not isinstance(item, dict):
            return (
                "Return one JSON object with keys stem, "
                f"options (exactly {option_count} strings), "
                "correct_index, explanation, subject, topic, difficulty."
            )
        missing = [k for k in ("stem", "options") if not item.get(k)]
        if missing:
            return (
                f"Previous JSON was missing required fields: {', '.join(missing)}. "
                f"Include stem and options with exactly {option_count} distinct "
                "non-empty strings."
            )
        options = item.get("options")
        if isinstance(options, list):
            return (
                f"The previous options array had {len(options)} items. "
                f"Return exactly {option_count} distinct options."
            )
        return (
            f"Return options as a JSON array containing exactly {option_count} strings."
        )

    @staticmethod
    def _prepare_mcq_item(
        item: Any,
        *,
        request: GenerateQuestionRequest,
        default_topic: str,
    ) -> dict[str, Any] | None:
        """Fill request-level defaults and reject obviously incomplete payloads."""
        if not isinstance(item, dict):
            return None
        # Skip obviously incomplete payloads before Pydantic (clearer logs/feedback)
        if not (item.get("stem") or item.get("question") or item.get("question_text")):
            logger.warning("mcq_item_skipped", error="missing stem")
            return None
        if item.get("options") is None and item.get("choices") is None:
            logger.warning("mcq_item_skipped", error="missing options")
            return None
        prepared = dict(item)
        if request.difficulty and not prepared.get("difficulty"):
            prepared["difficulty"] = request.difficulty
        if request.subject and not prepared.get("subject"):
            prepared["subject"] = request.subject
        if not prepared.get("topic"):
            prepared["topic"] = default_topic
        return prepared

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
            prepared = self._prepare_mcq_item(
                item, request=request, default_topic=default_topic
            )
            if prepared is None:
                continue
            try:
                valid.append(GeneratedMCQ.model_validate(prepared))
            except Exception as exc:
                logger.warning("mcq_item_skipped", error=str(exc))
        return valid

    def _parse_question_set(
        self,
        raw: dict[str, Any],
        *,
        request: GenerateQuestionRequest,
        default_topic: str,
        expected: int,
    ) -> GeneratedQuestionSet | None:
        """Parse a shared-stimulus payload: directions + passage + linked questions."""
        if not isinstance(raw, dict):
            return None
        items_raw = raw.get("questions")
        if not isinstance(items_raw, list) or not items_raw:
            logger.warning("question_set_skipped", error="missing questions array")
            return None

        questions: list[GeneratedMCQ] = []
        for item in items_raw:
            prepared = self._prepare_mcq_item(
                item, request=request, default_topic=default_topic
            )
            if prepared is None:
                continue
            try:
                questions.append(GeneratedMCQ.model_validate(prepared))
            except Exception as exc:
                logger.warning("mcq_item_skipped", error=str(exc))
        if not questions:
            return None

        passage = ""
        for key in ("passage", "context", "stimulus", "paragraph", "information"):
            value = raw.get(key)
            if isinstance(value, list):
                value = "\n".join(str(v).strip() for v in value if str(v).strip())
            if value and str(value).strip():
                passage = str(value).strip()
                break
        if not passage:
            logger.warning("question_set_skipped", error="missing passage")
            return None

        try:
            return GeneratedQuestionSet(
                directions=raw.get("directions") or raw.get("instructions") or "",
                passage=passage,
                questions=questions[:expected],
            )
        except Exception as exc:
            logger.warning("question_set_skipped", error=str(exc))
            return None

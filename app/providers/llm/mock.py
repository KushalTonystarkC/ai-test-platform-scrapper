"""Mock LLM provider for local development and tests."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from app.providers.llm.base import LLMProvider
from app.schemas.document import ChunkMetadata
from app.utils.json_utils import safe_parse_json

# Backwards-compatible alias used by older imports
_safe_parse_json = safe_parse_json


class MockLLMProvider(LLMProvider):
    """Deterministic mock that extracts lightweight heuristics from text."""

    _MOCK_STEMS = [
        "Which body regulates commercial banks in India?",
        "What is the primary function of monetary policy?",
        "Which institution manages India's foreign exchange reserves?",
        "What does the repo rate influence in the economy?",
        "Which body regulates the securities market in India?",
        "What is the main objective of priority sector lending?",
        "Which act governs banking regulation in India?",
        "What does CRR stand for in banking terms?",
    ]

    async def generate_json(
        self,
        prompt: str,
        *,
        system: str | None = None,
        schema_hint: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        seed: int | None = None,
    ) -> dict[str, Any]:
        digest = hashlib.sha256(prompt.encode()).hexdigest()[:12]
        is_mcq = bool(
            schema_hint
            and (
                "questions" in schema_hint
                or ("stem" in schema_hint and "options" in schema_hint)
            )
        )
        if is_mcq:
            # Vary the stem per prompt/seed so mock runs don't produce identical MCQs.
            selector = seed if seed is not None else int(digest, 16)
            stem = self._MOCK_STEMS[selector % len(self._MOCK_STEMS)]
            return {
                "stem": stem,
                "options": ["SEBI", "RBI", "IRDAI", "PFRDA"],
                "correct_index": 1,
                "explanation": "RBI is the banking regulator.",
                "subject": "Banking Awareness",
                "topic": "RBI",
                "difficulty": "easy",
            }
        return {"mock": True, "digest": digest, "prompt_length": len(prompt)}

    async def summarize(self, text: str, *, max_words: int = 100) -> str:
        words = text.split()
        snippet = " ".join(words[: min(max_words, 40)])
        return f"{snippet}…" if len(words) > 40 else snippet

    async def extract_metadata(
        self,
        text: str,
        *,
        source_type: str = "",
        exam_code: str = "",
    ) -> ChunkMetadata:
        words = re.findall(r"[A-Za-z][A-Za-z\-]{3,}", text)
        keywords = list(dict.fromkeys(w.lower() for w in words))[:12]
        concepts = list(dict.fromkeys(w for w in words if w[0].isupper()))[:8]
        summary = await self.summarize(text, max_words=60)
        return ChunkMetadata(
            subject="",
            chapter="",
            topic=concepts[0] if concepts else (keywords[0] if keywords else ""),
            subtopics=keywords[:5],
            keywords=keywords,
            concepts=concepts,
            learningObjectives=[],
            summary=summary,
            difficultyHint="medium",
            sourceType=source_type or "",
        )

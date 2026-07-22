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

    async def generate_json(
        self,
        prompt: str,
        *,
        system: str | None = None,
        schema_hint: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        digest = hashlib.sha256(prompt.encode()).hexdigest()[:12]
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

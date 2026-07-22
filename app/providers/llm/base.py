"""Abstract LLM provider interface — swappable implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.schemas.document import ChunkMetadata


class LLMProvider(ABC):
    """Interface for language model operations used by the knowledge base."""

    @abstractmethod
    async def generate_json(
        self,
        prompt: str,
        *,
        system: str | None = None,
        schema_hint: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate a JSON object from the given prompt. Returns parsed dict."""

    @abstractmethod
    async def summarize(self, text: str, *, max_words: int = 100) -> str:
        """Produce a concise summary of the given text."""

    @abstractmethod
    async def extract_metadata(
        self,
        text: str,
        *,
        source_type: str = "",
        exam_code: str = "",
    ) -> ChunkMetadata:
        """Extract structured educational metadata from a text chunk."""

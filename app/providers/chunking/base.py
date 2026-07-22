"""Semantic chunking interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.providers.pdf.base import ExtractedDocument


@dataclass(frozen=True, slots=True)
class TextChunk:
    content: str
    page_number: int  # primary / starting page
    chunk_index: int
    word_count: int
    end_page_number: int | None = None


class Chunker(ABC):
    @abstractmethod
    def chunk(self, document: ExtractedDocument) -> list[TextChunk]:
        """Split extracted document into semantic chunks."""

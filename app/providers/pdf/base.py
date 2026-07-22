"""PDF text extraction interface and page-aware models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PageText:
    page_number: int  # 1-indexed
    text: str


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    pages: list[PageText] = field(default_factory=list)
    page_count: int = 0

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.text for p in self.pages if p.text.strip())


class PDFExtractor(ABC):
    @abstractmethod
    async def extract(self, path: Path) -> ExtractedDocument:
        """Extract text from a PDF, preserving page numbers."""

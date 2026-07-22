"""pypdf-based PDF text extractor."""

from __future__ import annotations

import asyncio
from pathlib import Path

from pypdf import PdfReader

from app.core.exceptions import ProcessingError
from app.core.logging import get_logger
from app.providers.pdf.base import ExtractedDocument, PageText, PDFExtractor
from app.utils.text import normalize_whitespace

logger = get_logger(__name__)


class PyPDFExtractor(PDFExtractor):
    async def extract(self, path: Path) -> ExtractedDocument:
        return await asyncio.to_thread(self._extract_sync, path)

    def _extract_sync(self, path: Path) -> ExtractedDocument:
        if not path.exists():
            raise ProcessingError(f"PDF not found: {path}")
        try:
            reader = PdfReader(str(path))
        except Exception as exc:
            raise ProcessingError(f"Failed to open PDF: {exc}") from exc

        pages: list[PageText] = []
        for idx, page in enumerate(reader.pages, start=1):
            try:
                raw = page.extract_text() or ""
            except Exception as exc:
                logger.warning("page_extract_failed", page=idx, error=str(exc))
                raw = ""
            text = normalize_whitespace(raw)
            pages.append(PageText(page_number=idx, text=text))

        logger.info("pdf_extracted", path=str(path), page_count=len(pages))
        return ExtractedDocument(pages=pages, page_count=len(pages))

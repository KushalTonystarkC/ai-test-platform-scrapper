"""Sentence-aware semantic chunker (500–800 words, paragraph-preserving)."""

from __future__ import annotations

import re

from app.core.config import Settings, get_settings
from app.providers.chunking.base import Chunker, TextChunk
from app.providers.pdf.base import ExtractedDocument, PageText
from app.utils.text import normalize_whitespace, word_count

# Split on sentence-ending punctuation followed by whitespace / end
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


class SemanticChunker(Chunker):
    """
    Builds chunks of roughly [min_words, max_words] without splitting mid-sentence.

    Strategy:
    1. Flatten pages into (page_number, sentence) stream.
    2. Accumulate sentences into a buffer.
    3. Flush when buffer reaches min_words and adding the next sentence would
       exceed max_words, or when buffer already exceeds max_words.
    4. Prefer paragraph breaks as soft boundaries when available.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        min_words: int | None = None,
        max_words: int | None = None,
    ) -> None:
        settings = settings or get_settings()
        self.min_words = min_words or settings.chunk_min_words
        self.max_words = max_words or settings.chunk_max_words
        if self.min_words > self.max_words:
            raise ValueError("min_words must be <= max_words")

    def chunk(self, document: ExtractedDocument) -> list[TextChunk]:
        sentences = self._sentences_with_pages(document.pages)
        if not sentences:
            return []

        chunks: list[TextChunk] = []
        buffer: list[tuple[int, str]] = []
        buffer_words = 0

        def flush() -> None:
            nonlocal buffer, buffer_words
            if not buffer:
                return
            content = normalize_whitespace(" ".join(s for _, s in buffer))
            pages = [p for p, _ in buffer]
            chunks.append(
                TextChunk(
                    content=content,
                    page_number=pages[0],
                    chunk_index=len(chunks),
                    word_count=word_count(content),
                    end_page_number=pages[-1] if pages[-1] != pages[0] else None,
                )
            )
            buffer = []
            buffer_words = 0

        for page_num, sentence in sentences:
            s_words = word_count(sentence)
            # Oversized single sentence: emit as its own chunk (never split mid-sentence)
            if s_words > self.max_words and not buffer:
                buffer = [(page_num, sentence)]
                buffer_words = s_words
                flush()
                continue

            would_exceed = buffer_words + s_words > self.max_words
            if would_exceed and buffer_words >= self.min_words:
                flush()

            buffer.append((page_num, sentence))
            buffer_words += s_words

            # Soft flush at paragraph-like boundaries once past min
            if buffer_words >= self.min_words and sentence.rstrip().endswith((".", "!", "?")):
                # Look-ahead not available; flush if comfortably in range
                if buffer_words >= (self.min_words + self.max_words) // 2:
                    flush()

        flush()
        return chunks

    def _sentences_with_pages(self, pages: list[PageText]) -> list[tuple[int, str]]:
        result: list[tuple[int, str]] = []
        for page in pages:
            text = normalize_whitespace(page.text)
            if not text:
                continue
            # Preserve paragraphs: split on blank lines first, then sentences
            paragraphs = re.split(r"\n{2,}", text)
            for para in paragraphs:
                para = normalize_whitespace(para)
                if not para:
                    continue
                parts = _SENTENCE_BOUNDARY.split(para)
                for part in parts:
                    part = part.strip()
                    if part:
                        result.append((page.page_number, part))
        return result

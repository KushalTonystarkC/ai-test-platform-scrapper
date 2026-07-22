"""Unit tests for text utilities and semantic chunking."""

from __future__ import annotations

from app.providers.chunking.semantic import SemanticChunker
from app.providers.pdf.base import ExtractedDocument, PageText
from app.utils.text import normalize_whitespace, word_count


def test_normalize_whitespace() -> None:
    assert normalize_whitespace("  hello   world \n\n\n foo  ") == "hello world\n\nfoo"
    assert normalize_whitespace("") == ""


def test_word_count() -> None:
    assert word_count("one two three") == 3
    assert word_count("") == 0


def test_chunker_respects_word_bounds(chunker: SemanticChunker, sample_extracted: ExtractedDocument) -> None:
    chunks = chunker.chunk(sample_extracted)
    assert len(chunks) >= 2
    for c in chunks:
        assert c.word_count > 0
        assert c.page_number >= 1
        # Soft upper bound: single oversized sentence may exceed max
        # but normal chunks should stay near max_words
        assert "." in c.content or c.word_count <= chunker.max_words * 2


def test_chunker_never_splits_sentence() -> None:
    chunker = SemanticChunker(min_words=5, max_words=15)
    long_sentence = " ".join(["word"] * 20) + "."
    doc = ExtractedDocument(
        pages=[PageText(page_number=1, text=long_sentence)],
        page_count=1,
    )
    chunks = chunker.chunk(doc)
    assert len(chunks) == 1
    assert chunks[0].content.endswith(".")


def test_chunker_empty_document(chunker: SemanticChunker) -> None:
    doc = ExtractedDocument(pages=[PageText(page_number=1, text="   ")], page_count=1)
    assert chunker.chunk(doc) == []

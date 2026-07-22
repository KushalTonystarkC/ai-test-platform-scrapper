"""Unit tests for mock providers."""

from __future__ import annotations

import pytest

from app.providers.embedding.mock import MockEmbeddingProvider
from app.providers.llm.mock import MockLLMProvider


@pytest.mark.asyncio
async def test_mock_embedding_deterministic(mock_embeddings: MockEmbeddingProvider) -> None:
    a = await mock_embeddings.generate_embedding("hello world")
    b = await mock_embeddings.generate_embedding("hello world")
    c = await mock_embeddings.generate_embedding("different")
    assert a == b
    assert a != c
    assert len(a) == mock_embeddings.dimension
    # Unit vector
    norm = sum(x * x for x in a) ** 0.5
    assert abs(norm - 1.0) < 1e-5


@pytest.mark.asyncio
async def test_mock_llm_extract_metadata(mock_llm: MockLLMProvider) -> None:
    text = "The Reserve Bank of India regulates monetary policy and banking systems."
    meta = await mock_llm.extract_metadata(text, source_type="BOOK", exam_code="IBPS_PO")
    assert meta.summary
    assert meta.sourceType == "BOOK"
    assert isinstance(meta.keywords, list)
    assert isinstance(meta.concepts, list)


@pytest.mark.asyncio
async def test_mock_llm_generate_json(mock_llm: MockLLMProvider) -> None:
    result = await mock_llm.generate_json("test prompt")
    assert result["mock"] is True
    assert "digest" in result

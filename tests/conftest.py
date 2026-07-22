"""Shared test fixtures."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.providers.chunking.semantic import SemanticChunker
from app.providers.embedding.mock import MockEmbeddingProvider
from app.providers.llm.mock import MockLLMProvider
from app.providers.pdf.base import ExtractedDocument, PageText


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="test",
        llm_provider="mock",
        embedding_provider="mock",
        embedding_dimension=32,
        embedding_model="mock",
        llm_model="mock",
        gemini_api_key="",
        chunk_min_words=20,
        chunk_max_words=40,
        upload_dir="./uploads_test",
        database_url="postgresql+asyncpg://kushal:0000@localhost:5433/question_bank_test",
        hybrid_keyword_weight=0.3,
        hybrid_semantic_weight=0.7,
    )


@pytest.fixture
def mock_llm() -> MockLLMProvider:
    return MockLLMProvider()


@pytest.fixture
def mock_embeddings(settings: Settings) -> MockEmbeddingProvider:
    return MockEmbeddingProvider(dimension=settings.embedding_dimension)


@pytest.fixture
def chunker(settings: Settings) -> SemanticChunker:
    return SemanticChunker(settings)


@pytest.fixture
def sample_extracted() -> ExtractedDocument:
    # Build enough sentences for multiple chunks at test word limits
    sentences = [
        f"Sentence number {i} discusses banking awareness and quantitative aptitude topics carefully."
        for i in range(1, 60)
    ]
    page1 = " ".join(sentences[:30])
    page2 = " ".join(sentences[30:])
    return ExtractedDocument(
        pages=[
            PageText(page_number=1, text=page1),
            PageText(page_number=2, text=page2),
        ],
        page_count=2,
    )

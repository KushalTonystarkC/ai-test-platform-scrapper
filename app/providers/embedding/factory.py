"""Embedding provider factory."""

from __future__ import annotations

from app.core.config import Settings, get_settings
from app.core.exceptions import ProviderError
from app.providers.embedding.base import EmbeddingProvider
from app.providers.embedding.gemini_provider import GeminiEmbeddingProvider
from app.providers.embedding.mock import MockEmbeddingProvider
from app.providers.embedding.openai_provider import OpenAIEmbeddingProvider


def create_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    settings = settings or get_settings()
    name = settings.embedding_provider.lower().strip()
    if name == "mock":
        return MockEmbeddingProvider(dimension=settings.embedding_dimension)
    if name == "gemini":
        return GeminiEmbeddingProvider(settings)
    if name == "openai":
        return OpenAIEmbeddingProvider(settings)
    raise ProviderError(
        f"Unknown embedding provider: {name}",
        details={"supported": ["mock", "gemini", "openai"]},
    )

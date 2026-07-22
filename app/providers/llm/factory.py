"""LLM provider factory."""

from __future__ import annotations

from app.core.config import Settings, get_settings
from app.core.exceptions import ProviderError
from app.providers.llm.base import LLMProvider
from app.providers.llm.gemini_provider import GeminiLLMProvider
from app.providers.llm.mock import MockLLMProvider
from app.providers.llm.openai_provider import OpenAILLMProvider


def create_llm_provider(settings: Settings | None = None) -> LLMProvider:
    settings = settings or get_settings()
    name = settings.llm_provider.lower().strip()
    if name == "mock":
        return MockLLMProvider()
    if name == "gemini":
        return GeminiLLMProvider(settings)
    if name == "openai":
        return OpenAILLMProvider(settings)
    raise ProviderError(
        f"Unknown LLM provider: {name}",
        details={"supported": ["mock", "gemini", "openai"]},
    )

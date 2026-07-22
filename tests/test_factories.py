"""Unit tests for provider factories and task dispatcher."""

from __future__ import annotations

import uuid

import pytest

from app.core.config import Settings
from app.core.exceptions import ProviderError
from app.providers.embedding.factory import create_embedding_provider
from app.providers.embedding.mock import MockEmbeddingProvider
from app.providers.llm.factory import create_llm_provider
from app.providers.llm.mock import MockLLMProvider
from app.providers.llm.openai_provider import OpenAILLMProvider
from app.workers.tasks import InMemoryTaskDispatcher, create_task_dispatcher


def test_create_mock_providers(settings: Settings) -> None:
    llm = create_llm_provider(settings)
    emb = create_embedding_provider(settings)
    assert isinstance(llm, MockLLMProvider)
    assert isinstance(emb, MockEmbeddingProvider)


def test_unknown_llm_provider(settings: Settings) -> None:
    settings.llm_provider = "does-not-exist"
    with pytest.raises(ProviderError):
        create_llm_provider(settings)


def test_ollama_provider_constructs_without_real_key(settings: Settings) -> None:
    settings.llm_provider = "ollama"
    settings.openai_api_key = ""
    settings.openai_base_url = "http://localhost:11434/v1"
    settings.llm_model = "llama3.2"
    assert isinstance(create_llm_provider(settings), OpenAILLMProvider)


def test_gemini_providers_require_api_key(settings: Settings) -> None:
    settings.llm_provider = "gemini"
    settings.embedding_provider = "gemini"
    settings.gemini_api_key = ""
    with pytest.raises(ProviderError, match="GEMINI_API_KEY"):
        create_llm_provider(settings)
    with pytest.raises(ProviderError, match="GEMINI_API_KEY"):
        create_embedding_provider(settings)


def test_gemini_providers_construct_with_key(settings: Settings) -> None:
    pytest.importorskip("google.genai")
    from app.providers.embedding.gemini_provider import GeminiEmbeddingProvider
    from app.providers.llm.gemini_provider import GeminiLLMProvider

    settings.llm_provider = "gemini"
    settings.embedding_provider = "gemini"
    settings.gemini_api_key = "test-key"
    settings.llm_model = "gemini-2.5-flash"
    settings.embedding_model = "gemini-embedding-001"
    settings.embedding_dimension = 1536
    assert isinstance(create_llm_provider(settings), GeminiLLMProvider)
    assert isinstance(create_embedding_provider(settings), GeminiEmbeddingProvider)


def test_sentence_transformers_provider_missing_pkg(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.embedding_provider = "sentence_transformers"
    settings.embedding_model = "BAAI/bge-small-en-v1.5"
    settings.embedding_dimension = 384

    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if name == "sentence_transformers" or name.startswith("sentence_transformers."):
            raise ImportError("simulated missing package")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ProviderError, match="sentence-transformers is not installed"):
        create_embedding_provider(settings)


def test_task_dispatcher_factory() -> None:
    dispatcher = create_task_dispatcher("in_memory")
    assert isinstance(dispatcher, InMemoryTaskDispatcher)


@pytest.mark.asyncio
async def test_in_memory_enqueue() -> None:
    dispatcher = InMemoryTaskDispatcher()
    task_id = await dispatcher.enqueue_document_processing(uuid.uuid4())
    assert task_id.startswith("inmem-")

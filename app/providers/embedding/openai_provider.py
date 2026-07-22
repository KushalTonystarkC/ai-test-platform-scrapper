"""OpenAI embeddings provider."""

from __future__ import annotations

import httpx

from app.core.config import Settings
from app.core.exceptions import ProviderError
from app.core.logging import get_logger
from app.providers.embedding.base import EmbeddingProvider

logger = get_logger(__name__)


def _is_local_base_url(base_url: str) -> bool:
    host = base_url.lower()
    return any(
        token in host
        for token in ("localhost", "127.0.0.1", "0.0.0.0", "host.docker.internal")
    )


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.openai_base_url.rstrip("/")
        self._api_key = settings.openai_api_key or "ollama"
        if not settings.openai_api_key and not _is_local_base_url(self._base_url):
            raise ProviderError(
                "OPENAI_API_KEY is required for remote OpenAI-compatible embedding providers",
                details={"provider": "openai", "base_url": self._base_url},
            )
        self._model = settings.embedding_model
        self._dimension = settings.embedding_dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    async def generate_embedding(self, text: str) -> list[float]:
        vectors = await self.generate_embeddings([text])
        return vectors[0]

    async def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": self._model, "input": texts}
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{self._base_url}/embeddings",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                # Sort by index to preserve order
                items = sorted(data["data"], key=lambda x: x["index"])
                return [item["embedding"] for item in items]
        except httpx.HTTPError as exc:
            logger.error("openai_embedding_http_error", error=str(exc))
            raise ProviderError(f"OpenAI embedding request failed: {exc}") from exc
        except (KeyError, TypeError) as exc:
            raise ProviderError(f"Unexpected embedding response: {exc}") from exc

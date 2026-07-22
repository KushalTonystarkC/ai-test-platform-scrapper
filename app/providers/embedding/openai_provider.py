"""OpenAI embeddings provider."""

from __future__ import annotations

import httpx

from app.core.config import Settings
from app.core.exceptions import ProviderError
from app.core.logging import get_logger
from app.providers.embedding.base import EmbeddingProvider

logger = get_logger(__name__)


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise ProviderError(
                "OPENAI_API_KEY is required for OpenAI embedding provider",
                details={"provider": "openai"},
            )
        self._api_key = settings.openai_api_key
        self._base_url = settings.openai_base_url.rstrip("/")
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

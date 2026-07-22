"""Google Gemini embedding provider via the official google-genai SDK."""

from __future__ import annotations

from google import genai
from google.genai import types

from app.core.config import Settings
from app.core.exceptions import ProviderError
from app.core.logging import get_logger
from app.providers.embedding.base import EmbeddingProvider

logger = get_logger(__name__)


class GeminiEmbeddingProvider(EmbeddingProvider):
    """Embedding provider using Gemini embed_content (async)."""

    def __init__(self, settings: Settings) -> None:
        if not settings.gemini_api_key:
            raise ProviderError(
                "GEMINI_API_KEY is required for Gemini embedding provider",
                details={"provider": "gemini"},
            )
        self._model = settings.embedding_model
        self._dimension = settings.embedding_dimension
        self._client = genai.Client(api_key=settings.gemini_api_key)

    @property
    def dimension(self) -> int:
        return self._dimension

    async def generate_embedding(self, text: str) -> list[float]:
        vectors = await self.generate_embeddings([text])
        return vectors[0]

    async def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = await self._client.aio.models.embed_content(
                model=self._model,
                contents=texts,
                config=types.EmbedContentConfig(
                    output_dimensionality=self._dimension,
                    task_type="RETRIEVAL_DOCUMENT",
                ),
            )
        except Exception as exc:
            logger.error("gemini_embedding_error", error=str(exc))
            raise ProviderError(f"Gemini embedding request failed: {exc}") from exc

        embeddings = getattr(response, "embeddings", None) or []
        if len(embeddings) != len(texts):
            raise ProviderError(
                "Unexpected Gemini embedding response count",
                details={"expected": len(texts), "got": len(embeddings)},
            )

        vectors: list[list[float]] = []
        for item in embeddings:
            values = list(getattr(item, "values", None) or [])
            if len(values) != self._dimension:
                raise ProviderError(
                    "Gemini embedding dimension mismatch",
                    details={"expected": self._dimension, "got": len(values)},
                )
            vectors.append(values)
        return vectors

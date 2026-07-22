"""Local open-source embeddings via sentence-transformers (no API key)."""

from __future__ import annotations

import asyncio
from functools import partial

from app.core.config import Settings
from app.core.exceptions import ProviderError
from app.core.logging import get_logger
from app.providers.embedding.base import EmbeddingProvider

logger = get_logger(__name__)

# Well-known model → dimension map (override with EMBEDDING_DIMENSION if needed)
_KNOWN_DIMENSIONS: dict[str, int] = {
    "BAAI/bge-small-en-v1.5": 384,
    "BAAI/bge-base-en-v1.5": 768,
    "sentence-transformers/all-MiniLM-L6-v2": 384,
    "sentence-transformers/all-mpnet-base-v2": 768,
    "nomic-ai/nomic-embed-text-v1.5": 768,
}


class SentenceTransformersEmbeddingProvider(EmbeddingProvider):
    """Runs a Hugging Face sentence-transformers model locally (CPU/GPU)."""

    def __init__(self, settings: Settings) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ProviderError(
                "sentence-transformers is not installed. "
                'Install with: pip install -e ".[sentence-transformers]"',
                details={"provider": "sentence_transformers"},
            ) from exc

        self._model_name = settings.embedding_model
        expected = _KNOWN_DIMENSIONS.get(self._model_name, settings.embedding_dimension)
        if settings.embedding_dimension != expected and self._model_name in _KNOWN_DIMENSIONS:
            logger.warning(
                "embedding_dimension_mismatch",
                configured=settings.embedding_dimension,
                model_default=expected,
                model=self._model_name,
            )
        self._dimension = settings.embedding_dimension

        logger.info("loading_sentence_transformer", model=self._model_name)
        try:
            self._model = SentenceTransformer(self._model_name)
        except Exception as exc:
            raise ProviderError(
                f"Failed to load embedding model '{self._model_name}': {exc}",
                details={"provider": "sentence_transformers", "model": self._model_name},
            ) from exc

        if hasattr(self._model, "get_embedding_dimension"):
            actual_dim = int(self._model.get_embedding_dimension())
        else:
            actual_dim = int(self._model.get_sentence_embedding_dimension())
        if actual_dim != self._dimension:
            raise ProviderError(
                f"Model '{self._model_name}' produces {actual_dim}-dim vectors, "
                f"but EMBEDDING_DIMENSION={self._dimension}. "
                f"Set EMBEDDING_DIMENSION={actual_dim} and re-run migrations.",
                details={
                    "provider": "sentence_transformers",
                    "model_dimension": actual_dim,
                    "configured_dimension": self._dimension,
                },
            )

    @property
    def dimension(self) -> int:
        return self._dimension

    async def generate_embedding(self, text: str) -> list[float]:
        vectors = await self.generate_embeddings([text])
        return vectors[0]

    async def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        loop = asyncio.get_running_loop()
        try:
            # encode is CPU/GPU bound — run off the event loop
            encode = partial(
                self._model.encode,
                texts,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            vectors = await loop.run_in_executor(None, encode)
        except Exception as exc:
            logger.error("sentence_transformers_encode_error", error=str(exc))
            raise ProviderError(f"Local embedding failed: {exc}") from exc
        return [v.tolist() for v in vectors]

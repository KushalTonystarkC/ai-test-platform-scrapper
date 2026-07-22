"""Abstract embedding provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Interface for text embedding generation."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Vector dimensionality produced by this provider."""

    @abstractmethod
    async def generate_embedding(self, text: str) -> list[float]:
        """Generate a single embedding vector for the given text."""

    async def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Batch embed; default loops — override for efficient batch APIs."""
        return [await self.generate_embedding(t) for t in texts]

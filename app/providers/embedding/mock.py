"""Deterministic mock embeddings for development and tests."""

from __future__ import annotations

import hashlib
import math
import struct

from app.providers.embedding.base import EmbeddingProvider


class MockEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dimension: int = 1536) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    async def generate_embedding(self, text: str) -> list[float]:
        """Hash-based pseudo-random unit vector — stable for identical inputs."""
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        # Expand digest via repeated hashing
        raw = bytearray()
        seed = digest
        while len(raw) < self._dimension * 4:
            seed = hashlib.sha256(seed).digest()
            raw.extend(seed)

        values: list[float] = []
        for i in range(self._dimension):
            (val,) = struct.unpack("f", bytes(raw[i * 4 : (i + 1) * 4]))
            # Map to [-1, 1] range roughly
            values.append(math.tanh(val))

        norm = math.sqrt(sum(v * v for v in values)) or 1.0
        return [v / norm for v in values]

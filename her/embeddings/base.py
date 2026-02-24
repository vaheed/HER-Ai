from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List


class EmbeddingProvider(ABC):
    """Interface for text embedding providers."""

    name: str

    @abstractmethod
    async def embed(self, text: str) -> List[float]:
        """Return embedding vector for input text."""


def normalize_dimensions(vector: List[float], dimensions: int) -> List[float]:
    """Pad or truncate vectors to match configured pgvector dimensions."""

    if dimensions <= 0:
        return vector
    if len(vector) == dimensions:
        return vector
    if len(vector) > dimensions:
        return vector[:dimensions]
    return vector + [0.0] * (dimensions - len(vector))

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from her.memory.store import MemoryStore
from her.memory.types import SemanticMemoryRecord


class SemanticMemoryStore:
    """Semantic memory service backed by persistent MemoryStore."""

    def __init__(self, memory_store: MemoryStore) -> None:
        self._memory_store = memory_store

    async def upsert_concept(
        self,
        concept: str,
        summary: str,
        episode_id: UUID,
        tags: Optional[List[str]] = None,
        embedding: Optional[List[float]] = None,
    ) -> SemanticMemoryRecord:
        """Create or reinforce a semantic concept."""

        return await self._memory_store.upsert_semantic_concept(
            concept=concept,
            summary=summary,
            episode_id=episode_id,
            tags=tags,
            embedding=embedding,
        )

    async def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        min_confidence: float = 0.0,
    ) -> List[SemanticMemoryRecord]:
        """Search semantically similar concepts by embedding distance."""

        return await self._memory_store.semantic_search(
            query_embedding=query_embedding,
            top_k=top_k,
            min_confidence=min_confidence,
        )

    async def decay_confidence(self, weekly_decay: float = 0.05) -> int:
        """Decay confidence for all semantic records."""

        return await self._memory_store.decay_semantic_confidence(weekly_decay=weekly_decay)

    async def all_records(self) -> List[SemanticMemoryRecord]:
        """Return all semantic records."""

        return await self._memory_store.list_semantic_records()

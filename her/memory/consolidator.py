from __future__ import annotations

from her.memory.semantic import SemanticMemoryStore


class MemoryConsolidator:
    """Consolidate semantic records by confidence threshold."""

    def __init__(self, semantic_store: SemanticMemoryStore, threshold: float = 0.8) -> None:
        self._semantic_store = semantic_store
        self._threshold = threshold

    async def consolidate(self) -> int:
        """Return count of high-confidence concepts considered consolidated."""

        records = await self._semantic_store.all_records()
        return sum(1 for record in records if record.confidence >= self._threshold)

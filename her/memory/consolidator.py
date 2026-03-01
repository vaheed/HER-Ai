from __future__ import annotations

from typing import Dict

from her.memory.semantic import SemanticMemoryStore


class MemoryConsolidator:
    """Consolidate overlapping semantic records by normalized concept identity."""

    def __init__(self, semantic_store: SemanticMemoryStore, confidence_threshold: float = 0.8) -> None:
        self._semantic_store = semantic_store
        self._confidence_threshold = confidence_threshold

    async def consolidate(self) -> int:
        """Merge duplicate concepts and return number of consolidation updates."""

        records = await self._semantic_store.all_records()
        canonical: Dict[str, str] = {}
        updates = 0

        for record in records:
            if record.confidence < self._confidence_threshold:
                continue
            key = _normalize(record.concept)
            existing_summary = canonical.get(key)
            if existing_summary is None:
                canonical[key] = record.summary
                continue
            if existing_summary == record.summary:
                continue
            merged_summary = f"{existing_summary} {record.summary}".strip()
            if merged_summary != record.summary:
                await self._semantic_store.upsert_concept(
                    concept=record.concept,
                    summary=merged_summary,
                    episode_id=record.source_episode_ids[0],
                    tags=record.tags,
                )
                updates += 1

        return updates



def _normalize(value: str) -> str:
    return " ".join(value.lower().split())

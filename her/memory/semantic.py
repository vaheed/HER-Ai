from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List
from uuid import UUID, uuid4


@dataclass
class SemanticMemoryRecord:
    id: UUID
    concept: str
    summary: str
    confidence: float = 1.0
    source_episode_ids: List[UUID] = field(default_factory=list)
    last_reinforced: datetime = field(default_factory=datetime.utcnow)
    tags: List[str] = field(default_factory=list)


class SemanticMemoryStore:
    """Simple in-memory semantic memory registry."""

    def __init__(self) -> None:
        self._records: Dict[UUID, SemanticMemoryRecord] = {}

    async def upsert_concept(self, concept: str, summary: str, episode_id: UUID) -> SemanticMemoryRecord:
        """Create or reinforce a semantic concept record."""

        for record in self._records.values():
            if record.concept.lower() == concept.lower():
                record.summary = summary
                record.confidence = min(1.0, record.confidence + 0.05)
                record.last_reinforced = datetime.utcnow()
                if episode_id not in record.source_episode_ids:
                    record.source_episode_ids.append(episode_id)
                return record

        record = SemanticMemoryRecord(
            id=uuid4(),
            concept=concept,
            summary=summary,
            confidence=1.0,
            source_episode_ids=[episode_id],
        )
        self._records[record.id] = record
        return record

    async def decay_confidence(self, weekly_decay: float = 0.05) -> None:
        """Decay confidence for semantic records."""

        for record in self._records.values():
            record.confidence = max(0.0, round(record.confidence - weekly_decay, 3))

    async def all_records(self) -> List[SemanticMemoryRecord]:
        """Return all semantic memory records."""

        return list(self._records.values())

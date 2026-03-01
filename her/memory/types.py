from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID


@dataclass
class SemanticMemoryRecord:
    """Semantic memory transfer object."""

    id: UUID
    concept: str
    summary: str
    confidence: float
    source_episode_ids: List[UUID] = field(default_factory=list)
    last_reinforced: datetime = field(default_factory=datetime.utcnow)
    created_at: datetime = field(default_factory=datetime.utcnow)
    tags: List[str] = field(default_factory=list)


@dataclass
class GoalRecord:
    """Goal transfer object."""

    id: UUID
    description: str
    status: str
    priority: float
    created_at: datetime
    last_progressed: datetime | None
    linked_episodes: List[UUID] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class PersonalitySnapshotRecord:
    """Personality snapshot transfer object."""

    snapshot_at: datetime
    traits: Dict[str, float]
    emotional_baseline: Dict[str, float | str | None]
    drift_delta: Optional[Dict[str, float]]
    trigger_summary: Optional[str]

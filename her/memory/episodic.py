from __future__ import annotations

from typing import Dict, List, Optional
from uuid import UUID

from her.memory.store import MemoryStore
from her.models import Episode


class EpisodicMemoryStore:
    """Episodic memory service backed by persistent MemoryStore."""

    def __init__(self, memory_store: MemoryStore) -> None:
        self._memory_store = memory_store

    async def add_episode(
        self,
        session_id: UUID,
        content: str,
        importance_score: float = 0.5,
        emotional_valence: float = 0.0,
        embedding: Optional[List[float]] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Episode:
        """Persist a new episodic memory entry."""

        return await self._memory_store.add_episode(
            session_id=session_id,
            content=content,
            importance_score=importance_score,
            emotional_valence=emotional_valence,
            embedding=embedding,
            metadata=metadata,
        )

    async def list_session_episodes(self, session_id: UUID, include_archived: bool = False) -> List[Episode]:
        """List episodes for a session."""

        return await self._memory_store.list_session_episodes(
            session_id=session_id,
            include_archived=include_archived,
        )

    async def decay_and_archive(self, daily_decay: float = 0.95) -> int:
        """Apply decay and archive rules."""

        return await self._memory_store.decay_and_archive_episodes(daily_decay=daily_decay)

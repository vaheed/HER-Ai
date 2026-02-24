from __future__ import annotations

from datetime import datetime
from typing import Dict, List
from uuid import UUID, uuid4

from her.models import Episode


class EpisodicMemoryStore:
    """In-memory episodic memory store with async CRUD surface."""

    def __init__(self) -> None:
        self._episodes: Dict[UUID, Episode] = {}

    async def add_episode(self, session_id: UUID, content: str, importance_score: float = 0.5) -> Episode:
        """Add a new episodic memory entry."""

        episode = Episode(
            id=uuid4(),
            session_id=session_id,
            timestamp=datetime.utcnow(),
            content=content,
            embedding=None,
            emotional_valence=0.0,
            importance_score=max(0.0, min(1.0, importance_score)),
            decay_factor=1.0,
            archived=False,
            metadata={},
        )
        self._episodes[episode.id] = episode
        return episode

    async def list_session_episodes(self, session_id: UUID) -> List[Episode]:
        """List episodic entries for a session."""

        return [episode for episode in self._episodes.values() if episode.session_id == session_id]

    async def decay_and_archive(self, daily_decay: float = 0.95) -> int:
        """Apply decay to all episodes and archive stale low-importance records."""

        archived = 0
        for episode in self._episodes.values():
            if episode.archived:
                continue
            new_decay = episode.decay_factor * daily_decay
            episode.decay_factor = round(new_decay, 4)
            if episode.decay_factor < 0.1 and episode.importance_score < 0.3:
                episode.archived = True
                archived += 1
        return archived

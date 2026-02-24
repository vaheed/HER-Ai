from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List
from uuid import UUID


class WorkingMemory:
    """Session-scoped short-term memory with TTL semantics."""

    def __init__(self, ttl_minutes: int = 30) -> None:
        self._ttl = timedelta(minutes=ttl_minutes)
        self._store: Dict[UUID, List[Dict[str, str]]] = {}
        self._expires_at: Dict[UUID, datetime] = {}

    async def append(self, session_id: UUID, role: str, content: str) -> None:
        """Append a message to session working memory."""

        self._cleanup(session_id)
        self._store.setdefault(session_id, []).append({"role": role, "content": content})
        self._expires_at[session_id] = datetime.utcnow() + self._ttl

    async def get(self, session_id: UUID) -> List[Dict[str, str]]:
        """Return active working memory messages for a session."""

        self._cleanup(session_id)
        return list(self._store.get(session_id, []))

    def _cleanup(self, session_id: UUID) -> None:
        expires = self._expires_at.get(session_id)
        if expires and datetime.utcnow() > expires:
            self._store.pop(session_id, None)
            self._expires_at.pop(session_id, None)

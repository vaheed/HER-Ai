from __future__ import annotations

from collections import defaultdict
from typing import Any


class FallbackMemory:
    """Minimal in-process memory fallback used when Mem0/DB is unavailable."""

    def __init__(self) -> None:
        self._contexts: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._memories: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def add_memory(self, user_id: str, text: str, category: str, importance: float) -> dict[str, Any]:
        entry = {
            "memory": text,
            "category": category,
            "importance": importance,
        }
        self._memories[user_id].append(entry)
        return {"status": "stored_in_fallback", "memory": entry}

    def search_memories(self, user_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        needle = query.lower().strip()
        items = self._memories.get(user_id, [])
        if not needle:
            return items[-limit:]

        matches = [
            item
            for item in items
            if needle in str(item.get("memory", "")).lower()
        ]
        return matches[-limit:] if matches else items[-limit:]

    def update_memory(self, memory_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        return {"status": "unsupported_in_fallback", "memory_id": memory_id, "updates": updates}

    def delete_memory(self, memory_id: str) -> dict[str, Any]:
        return {"status": "unsupported_in_fallback", "memory_id": memory_id}

    def get_context(self, user_id: str) -> list[dict[str, Any]]:
        return list(self._contexts.get(user_id, []))

    def update_context(self, user_id: str, message: str, role: str, max_messages: int = 20) -> list[dict[str, Any]]:
        context = self._contexts[user_id]
        context.append({"role": role, "message": message})
        self._contexts[user_id] = context[-max_messages:]
        return list(self._contexts[user_id])

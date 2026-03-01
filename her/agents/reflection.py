from __future__ import annotations

from her.models import PersonalityVector
from her.memory.store import MemoryStore
from her.personality.manager import PersonalityManager


class ReflectionAgent:
    """Run reflection cycles over memory and personality."""

    def __init__(self, memory_store: MemoryStore, personality_manager: PersonalityManager) -> None:
        self._memory_store = memory_store
        self._personality = personality_manager

    async def run_daily_reflection(self, vector: PersonalityVector | None = None) -> PersonalityVector:
        """Decay memory and apply a weekly-style regression step."""

        await self._memory_store.decay_and_archive_episodes()
        await self._memory_store.decay_semantic_confidence()
        await self._memory_store.flag_dormant_goals()
        return await self._personality.weekly_regression()

from __future__ import annotations

from her.personality.drift_engine import DriftEngine
from her.models import PersonalityVector
from her.memory.store import MemoryStore


class ReflectionAgent:
    """Run reflection cycles over memory and personality."""

    def __init__(self, memory_store: MemoryStore, drift_engine: DriftEngine) -> None:
        self._memory_store = memory_store
        self._drift = drift_engine

    async def run_daily_reflection(self, vector: PersonalityVector) -> PersonalityVector:
        """Decay memory and apply a weekly-style regression step."""

        await self._memory_store.decay_and_archive_episodes()
        await self._memory_store.decay_semantic_confidence()
        await self._memory_store.flag_dormant_goals()
        return self._drift.weekly_regress(vector)

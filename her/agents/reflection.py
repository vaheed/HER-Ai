from __future__ import annotations

from her.memory.episodic import EpisodicMemoryStore
from her.personality.drift_engine import DriftEngine
from her.models import PersonalityVector


class ReflectionAgent:
    """Run reflection cycles over memory and personality."""

    def __init__(self, episodic_store: EpisodicMemoryStore, drift_engine: DriftEngine) -> None:
        self._episodic = episodic_store
        self._drift = drift_engine

    async def run_daily_reflection(self, vector: PersonalityVector) -> PersonalityVector:
        """Decay memory and apply a weekly-style regression step."""

        await self._episodic.decay_and_archive()
        return self._drift.weekly_regress(vector)

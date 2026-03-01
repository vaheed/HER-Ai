from __future__ import annotations

import asyncio
from pathlib import Path

from her.agents.reflection import ReflectionAgent
from her.config.settings import get_settings
from her.memory.db import MemoryDatabase
from her.memory.store import MemoryStore
from her.personality.drift_engine import DriftEngine
from her.personality.manager import PersonalityManager
from her.personality.vector import load_drift_config, load_emotional_baseline, load_personality_baseline


async def main() -> None:
    """Run a reflection cycle: memory aging plus personality regression."""

    settings = get_settings()
    database = MemoryDatabase(settings.database_url)
    store = MemoryStore(database)

    config_path = Path(__file__).resolve().parents[1] / "her" / "config" / "personality_baseline.yaml"
    baseline = load_personality_baseline(config_path)
    emotional = load_emotional_baseline(config_path)
    drift_config = load_drift_config(config_path)
    manager = PersonalityManager(
        baseline_personality=baseline,
        baseline_emotion=emotional,
        drift_engine=DriftEngine(baseline, config=drift_config),
        snapshot_store=store,
    )
    reflection = ReflectionAgent(memory_store=store, personality_manager=manager)

    updated_vector = await reflection.run_daily_reflection()
    print(updated_vector.model_dump_json(indent=2))
    await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())

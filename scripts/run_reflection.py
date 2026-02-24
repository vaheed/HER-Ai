from __future__ import annotations

import asyncio
from pathlib import Path

from her.agents.reflection import ReflectionAgent
from her.config.settings import get_settings
from her.memory.db import MemoryDatabase
from her.memory.store import MemoryStore
from her.personality.drift_engine import DriftEngine
from her.personality.vector import load_personality_baseline


async def main() -> None:
    """Run a reflection cycle: memory aging plus personality regression."""

    settings = get_settings()
    database = MemoryDatabase(settings.database_url)
    store = MemoryStore(database)

    config_path = Path(__file__).resolve().parents[1] / "her" / "config" / "personality_baseline.yaml"
    baseline = load_personality_baseline(config_path)
    reflection = ReflectionAgent(memory_store=store, drift_engine=DriftEngine(baseline))

    updated_vector = await reflection.run_daily_reflection(baseline)
    print(updated_vector.model_dump_json(indent=2))
    await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())

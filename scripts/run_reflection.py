from __future__ import annotations

import asyncio
from pathlib import Path

from her.agents.reflection import ReflectionAgent
from her.memory.episodic import EpisodicMemoryStore
from her.personality.drift_engine import DriftEngine
from her.personality.vector import load_personality_baseline


async def main() -> None:
    """Run a local reflection cycle and print the resulting vector."""

    config_path = Path(__file__).resolve().parents[1] / "her" / "config" / "personality_baseline.yaml"
    baseline = load_personality_baseline(config_path)
    reflection = ReflectionAgent(EpisodicMemoryStore(), DriftEngine(baseline))
    updated = await reflection.run_daily_reflection(baseline)
    print(updated.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())

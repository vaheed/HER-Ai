from __future__ import annotations

import asyncio
from uuid import uuid4

from her.memory.episodic import EpisodicMemoryStore


async def main() -> None:
    """Seed in-memory episodic store for local development."""

    store = EpisodicMemoryStore()
    session_id = uuid4()
    await store.add_episode(session_id=session_id, content="User likes concise answers", importance_score=0.8)
    episodes = await store.list_session_episodes(session_id)
    print(f"Seeded episodes: {len(episodes)}")


if __name__ == "__main__":
    asyncio.run(main())

from __future__ import annotations

import asyncio
from uuid import uuid4

from her.config.settings import get_settings
from her.memory.db import MemoryDatabase
from her.memory.store import MemoryStore


async def main() -> None:
    """Seed persistent memory tables with initial sample records."""

    settings = get_settings()
    database = MemoryDatabase(settings.database_url)
    store = MemoryStore(database)

    session_id = uuid4()
    episode = await store.add_episode(
        session_id=session_id,
        content="User likes concise answers and practical implementation steps.",
        importance_score=0.85,
    )
    await store.upsert_semantic_concept(
        concept="response style",
        summary="The user prefers concise and pragmatic responses.",
        episode_id=episode.id,
        tags=["style", "preference"],
    )
    await store.create_goal("Maintain concise, practical answer style", priority=0.9)

    episodes = await store.list_session_episodes(session_id)
    print(f"Seeded episodes for session {session_id}: {len(episodes)}")
    await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())

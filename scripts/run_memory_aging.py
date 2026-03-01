from __future__ import annotations

import asyncio

from her.config.settings import get_settings
from her.memory.db import MemoryDatabase
from her.memory.store import MemoryStore


async def main() -> None:
    """Run memory aging and dormancy tasks."""

    settings = get_settings()
    database = MemoryDatabase(settings.database_url)
    store = MemoryStore(database)

    archived = await store.decay_and_archive_episodes(daily_decay=0.95)
    semantic_updated = await store.decay_semantic_confidence(weekly_decay=0.05)
    dormant_goals = await store.flag_dormant_goals(days_without_progress=14)

    print(
        "Aging results:",
        {
            "archived_episodes": archived,
            "updated_semantic_records": semantic_updated,
            "dormant_goals": dormant_goals,
        },
    )
    await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())

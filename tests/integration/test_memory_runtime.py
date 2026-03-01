from __future__ import annotations

from uuid import uuid4

import pytest
from redis.asyncio import Redis

from her.config.settings import Settings
from her.memory.db import MemoryDatabase
from her.memory.store import MemoryStore
from her.memory.working import WorkingMemory


@pytest.mark.asyncio
async def test_memory_store_with_live_postgres_and_redis() -> None:
    settings = Settings()

    database = MemoryDatabase(settings.database_url)
    if not await database.healthcheck():
        await database.dispose()
        pytest.skip("Postgres is not available for integration test")

    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        await redis.ping()
    except Exception:
        await redis.aclose()
        await database.dispose()
        pytest.skip("Redis is not available for integration test")

    store = MemoryStore(database)
    session_id = uuid4()

    episode = await store.add_episode(
        session_id=session_id,
        content="Integration test: persistent memory write",
        importance_score=0.7,
    )
    episodes = await store.list_session_episodes(session_id)
    assert any(item.id == episode.id for item in episodes)

    vector = [0.01] * settings.embedding_dimensions
    concept = await store.upsert_semantic_concept(
        concept="integration-memory",
        summary="integration semantic record",
        episode_id=episode.id,
        embedding=vector,
    )
    search_results = await store.semantic_search(query_embedding=vector, top_k=3)
    assert any(item.id == concept.id for item in search_results)

    working_memory = WorkingMemory(settings.redis_url, ttl_minutes=5)
    await working_memory.append(session_id=session_id, role="user", content="hello integration")
    messages = await working_memory.get(session_id=session_id)
    assert messages and messages[-1]["content"] == "hello integration"

    await working_memory.close()
    await redis.aclose()
    await database.dispose()

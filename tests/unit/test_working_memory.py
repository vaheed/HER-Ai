from __future__ import annotations

from uuid import uuid4

import pytest

from her.memory.working import WorkingMemory


@pytest.mark.asyncio
async def test_working_memory_falls_back_when_redis_unavailable() -> None:
    memory = WorkingMemory(redis_url="redis://127.0.0.1:1/0", ttl_minutes=1)
    session_id = uuid4()

    await memory.append(session_id=session_id, role="user", content="hello")
    messages = await memory.get(session_id=session_id)

    assert messages == [{"role": "user", "content": "hello"}]
    await memory.close()

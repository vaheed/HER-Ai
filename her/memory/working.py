from __future__ import annotations

import json
import time
from collections.abc import Awaitable
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, TypeVar, cast
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from her.observability.logging import get_logger


class WorkingMemory:
    """Redis-backed session working memory with in-process fallback."""

    def __init__(self, redis_url: str, ttl_minutes: int = 30, stream_name: str = "her:events") -> None:
        self._redis_url = redis_url
        self._ttl = timedelta(minutes=ttl_minutes)
        self._ttl_seconds = int(self._ttl.total_seconds())
        self._stream_name = stream_name
        self._client: Optional[Redis] = None
        self._fallback_store: Dict[UUID, List[Dict[str, str]]] = {}
        self._fallback_expires_at: Dict[UUID, datetime] = {}
        self._logger = get_logger("working_memory")

    async def append(self, session_id: UUID, role: str, content: str) -> None:
        """Append a message to working memory and extend TTL."""

        client = await self._get_client()
        if client is None:
            self._append_fallback(session_id=session_id, role=role, content=content)
            return

        key = _session_key(session_id)
        field = str(time.time_ns())
        payload = json.dumps({"role": role, "content": content})

        await _await_maybe(client.hset(key, field, payload))
        await _await_maybe(client.expire(key, self._ttl_seconds))

    async def get(self, session_id: UUID) -> List[Dict[str, str]]:
        """Return session messages ordered by append time."""

        client = await self._get_client()
        if client is None:
            self._cleanup_fallback(session_id)
            return list(self._fallback_store.get(session_id, []))

        key = _session_key(session_id)
        raw = await _await_maybe(client.hgetall(key))
        if not raw:
            return []

        items = sorted(raw.items(), key=lambda pair: int(pair[0]))
        messages: List[Dict[str, str]] = []
        for _, payload in items:
            decoded = json.loads(payload)
            role = str(decoded.get("role", "assistant"))
            content = str(decoded.get("content", ""))
            messages.append({"role": role, "content": content})

        await _await_maybe(client.expire(key, self._ttl_seconds))
        return messages

    async def emit_event(self, event_type: str, payload: Dict[str, str]) -> None:
        """Emit a memory-related event to Redis Streams."""

        client = await self._get_client()
        if client is None:
            return

        event_payload: Dict[str, str] = {"type": event_type, **payload}
        await _await_maybe(client.xadd(self._stream_name, cast(Dict[Any, Any], event_payload)))

    async def close(self) -> None:
        """Close underlying Redis connection if initialized."""

        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get_client(self) -> Optional[Redis]:
        if self._client is not None:
            return self._client

        try:
            client = Redis.from_url(self._redis_url, decode_responses=True)
            await _await_maybe(client.ping())
            self._client = client
            self._logger.info("working_memory_redis_connected", redis_url=self._redis_url)
            return self._client
        except (RedisError, OSError) as exc:
            self._logger.warning("working_memory_redis_unavailable", error=str(exc))
            return None

    def _append_fallback(self, session_id: UUID, role: str, content: str) -> None:
        self._cleanup_fallback(session_id)
        self._fallback_store.setdefault(session_id, []).append({"role": role, "content": content})
        self._fallback_expires_at[session_id] = datetime.utcnow() + self._ttl

    def _cleanup_fallback(self, session_id: UUID) -> None:
        expires = self._fallback_expires_at.get(session_id)
        if expires and datetime.utcnow() > expires:
            self._fallback_store.pop(session_id, None)
            self._fallback_expires_at.pop(session_id, None)



def _session_key(session_id: UUID) -> str:
    return f"her:wm:{session_id}"


T = TypeVar("T")


async def _await_maybe(value: Awaitable[T] | T) -> T:
    """Await value when redis stubs expose sync/async union return types."""

    if hasattr(value, "__await__"):
        return await cast(Awaitable[T], value)
    return value

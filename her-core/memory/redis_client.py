import json
from typing import Any

import redis


class RedisContextStore:
    def __init__(self, host: str, port: int, password: str, ttl_seconds: int = 86400) -> None:
        self._client = redis.Redis(
            host=host,
            port=port,
            password=password,
            decode_responses=True,
        )
        self._ttl = ttl_seconds

    def get(self, key: str) -> list[dict[str, Any]]:
        raw = self._client.get(key)
        if not raw:
            return []
        return json.loads(raw)

    def set(self, key: str, value: list[dict[str, Any]]) -> None:
        payload = json.dumps(value)
        self._client.setex(key, self._ttl, payload)

    def append(self, key: str, entry: dict[str, Any], max_entries: int) -> list[dict[str, Any]]:
        data = self.get(key)
        data.append(entry)
        data = data[-max_entries:]
        self.set(key, data)
        return data

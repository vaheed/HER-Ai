import json
import logging
import re
from datetime import datetime, timezone

import redis

TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return len(TOKEN_PATTERN.findall(text))


class HERMetrics:
    def __init__(self, host: str, port: int, password: str) -> None:
        self._client = redis.Redis(
            host=host,
            port=port,
            password=password,
            decode_responses=True,
        )
        self._logger = logging.getLogger("her-metrics")

    def record_interaction(self, user_id: str, user_message: str, response_message: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        token_estimate = estimate_tokens(user_message) + estimate_tokens(response_message)
        payload = {
            "timestamp": now,
            "user_id": user_id,
            "user_message": user_message,
            "response_message": response_message,
            "token_estimate": token_estimate,
        }

        try:
            pipeline = self._client.pipeline()
            pipeline.incrby("her:metrics:tokens", token_estimate)
            pipeline.incr("her:metrics:messages")
            pipeline.sadd("her:metrics:users", user_id)
            pipeline.set("her:metrics:last_response", json.dumps(payload))
            pipeline.lpush("her:metrics:events", json.dumps(payload))
            pipeline.ltrim("her:metrics:events", 0, 49)
            pipeline.execute()
        except redis.RedisError as exc:
            self._logger.warning("Failed to record metrics: %s", exc)

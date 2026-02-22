from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class DecisionLogger:
    """Persist operational decisions/events for transparency."""

    def __init__(self) -> None:
        self._redis_client = None
        self._postgres_enabled = str(os.getenv("HER_DECISION_LOG_POSTGRES_ENABLED", "true")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self._postgres_failures = 0
        self._postgres_backoff_until = 0.0
        try:
            import redis

            self._redis_client = redis.Redis(
                host=os.getenv("REDIS_HOST", "redis"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                password=os.getenv("REDIS_PASSWORD", ""),
                decode_responses=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Decision logger Redis unavailable: %s", exc)

    def log(
        self,
        event_type: str,
        summary: str,
        user_id: str | None = None,
        source: str = "runtime",
        details: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "summary": summary,
            "user_id": user_id or "",
            "source": source,
            "details": details or {},
        }
        self._write_redis(payload)
        self._write_postgres(payload)

    def _write_redis(self, payload: dict[str, Any]) -> None:
        if self._redis_client is None:
            return
        try:
            self._redis_client.lpush("her:decision:logs", json.dumps(payload))
            self._redis_client.ltrim("her:decision:logs", 0, 499)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Decision logger Redis write failed: %s", exc)

    def _write_postgres(self, payload: dict[str, Any]) -> None:
        if not self._postgres_enabled:
            return
        if time.monotonic() < self._postgres_backoff_until:
            return
        try:
            import psycopg2

            connection = psycopg2.connect(
                dbname=os.getenv("POSTGRES_DB", "her_memory"),
                user=os.getenv("POSTGRES_USER", "her"),
                password=os.getenv("POSTGRES_PASSWORD", ""),
                host=os.getenv("POSTGRES_HOST", "postgres"),
                port=int(os.getenv("POSTGRES_PORT", "5432")),
            )
            try:
                with connection:
                    with connection.cursor() as cursor:
                        user_id = str(payload.get("user_id", "") or "").strip()
                        if user_id:
                            cursor.execute(
                                """
                                INSERT INTO users (user_id, last_interaction)
                                VALUES (%s, NOW())
                                ON CONFLICT (user_id)
                                DO UPDATE SET last_interaction = EXCLUDED.last_interaction
                                """,
                                (user_id,),
                            )
                        cursor.execute(
                            """
                            INSERT INTO decision_logs (event_type, user_id, source, summary, details)
                            VALUES (%s, NULLIF(%s, ''), %s, %s, %s::jsonb)
                            """,
                            (
                                payload.get("event_type", ""),
                                user_id,
                                payload.get("source", "runtime"),
                                payload.get("summary", ""),
                                json.dumps(payload.get("details", {})),
                            ),
                        )
            finally:
                connection.close()
            self._postgres_failures = 0
            self._postgres_backoff_until = 0.0
        except Exception as exc:  # noqa: BLE001
            self._postgres_failures += 1
            backoff_seconds = min(60, 2 ** min(self._postgres_failures, 6))
            self._postgres_backoff_until = time.monotonic() + float(backoff_seconds)
            logger.debug("Decision logger Postgres write skipped: %s", exc)

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

    def record_log(self, level: str, message: str, **kwargs) -> None:
        """Record a log entry to Redis."""
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "timestamp": now,
            "level": level,
            "message": message,
            **kwargs,
        }

        try:
            self._client.lpush("her:logs", json.dumps(payload))
            self._client.ltrim("her:logs", 0, 199)  # Keep last 200 logs
        except redis.RedisError as exc:
            self._logger.warning("Failed to record log: %s", exc)

    def record_sandbox_execution(
        self,
        command: str,
        success: bool,
        output: str,
        error: str,
        exit_code: int,
        execution_time: float,
        user: str = "sandbox",
        workdir: str = "/workspace",
    ) -> None:
        """Record sandbox execution to Redis."""
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "timestamp": now,
            "command": command,
            "success": success,
            "output": output,
            "error": error,
            "exit_code": exit_code,
            "execution_time": execution_time,
            "user": user,
            "workdir": workdir,
        }

        try:
            self._client.lpush("her:sandbox:executions", json.dumps(payload))
            self._client.ltrim("her:sandbox:executions", 0, 99)  # Keep last 100 executions
        except redis.RedisError as exc:
            self._logger.warning("Failed to record sandbox execution: %s", exc)

    def record_scheduled_job(
        self,
        name: str,
        job_type: str,
        success: bool,
        result: str = "",
        error: str = "",
        execution_time: float = 0.0,
        next_run: str = "",
    ) -> None:
        """Record scheduled job execution to Redis."""
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "timestamp": now,
            "name": name,
            "type": job_type,
            "success": success,
            "result": result,
            "error": error,
            "execution_time": execution_time,
            "next_run": next_run,
        }

        try:
            self._client.lpush("her:scheduler:jobs", json.dumps(payload))
            self._client.ltrim("her:scheduler:jobs", 0, 99)  # Keep last 100 jobs
        except redis.RedisError as exc:
            self._logger.warning("Failed to record scheduled job: %s", exc)

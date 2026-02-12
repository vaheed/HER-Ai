import time
from collections import defaultdict
from typing import Dict


class RateLimiter:
    """Token bucket rate limiter for public users."""

    def __init__(self, messages_per_minute: int, messages_per_hour: int):
        self.messages_per_minute = messages_per_minute
        self.messages_per_hour = messages_per_hour
        self.buckets: Dict[int, dict] = defaultdict(
            lambda: {
                "minute_tokens": messages_per_minute,
                "hour_tokens": messages_per_hour,
                "last_reset_minute": time.time(),
                "last_reset_hour": time.time(),
            }
        )

    def is_allowed(self, user_id: int) -> bool:
        now = time.time()
        bucket = self.buckets[user_id]

        if now - bucket["last_reset_minute"] >= 60:
            bucket["minute_tokens"] = self.messages_per_minute
            bucket["last_reset_minute"] = now

        if now - bucket["last_reset_hour"] >= 3600:
            bucket["hour_tokens"] = self.messages_per_hour
            bucket["last_reset_hour"] = now

        if bucket["minute_tokens"] <= 0 or bucket["hour_tokens"] <= 0:
            return False

        bucket["minute_tokens"] -= 1
        bucket["hour_tokens"] -= 1
        return True

    def reset_user(self, user_id: int):
        self.buckets[user_id] = {
            "minute_tokens": self.messages_per_minute,
            "hour_tokens": self.messages_per_hour,
            "last_reset_minute": time.time(),
            "last_reset_hour": time.time(),
        }

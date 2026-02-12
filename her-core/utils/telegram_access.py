import time

import redis


class TelegramAccessController:
    def __init__(
        self,
        host: str,
        port: int,
        password: str,
        admin_user_ids: set[str],
        approval_required: bool,
        public_rate_limit_per_minute: int,
    ) -> None:
        self._client = redis.Redis(host=host, port=port, password=password, decode_responses=True)
        self._admin_user_ids = admin_user_ids
        self._approval_required = approval_required
        self._public_rate_limit_per_minute = public_rate_limit_per_minute

    def is_admin(self, user_id: str) -> bool:
        return user_id in self._admin_user_ids

    def is_approved(self, user_id: str) -> bool:
        if self.is_admin(user_id):
            return True
        if not self._approval_required:
            return True
        return bool(self._client.sismember("her:telegram:approved_users", user_id))

    def approve_user(self, user_id: str) -> None:
        self._client.sadd("her:telegram:approved_users", user_id)

    def can_send_message(self, user_id: str) -> tuple[bool, str | None]:
        if not self.is_approved(user_id):
            return False, "not_approved"

        if self.is_admin(user_id):
            return True, None

        current_minute = int(time.time() // 60)
        key = f"her:telegram:rate_limit:{user_id}:{current_minute}"
        count = self._client.incr(key)
        if count == 1:
            self._client.expire(key, 70)

        if count > self._public_rate_limit_per_minute:
            return False, "rate_limited"
        return True, None

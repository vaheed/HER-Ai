from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


def _safe_timezone_name(value: str, fallback: str = "UTC") -> str:
    candidate = (value or fallback).strip() or fallback
    try:
        ZoneInfo(candidate)
        return candidate
    except Exception:  # noqa: BLE001
        return fallback


@dataclass
class RuntimeUserProfile:
    user_id: str
    chat_id: int | None
    timezone: str
    telegram_user_id: int | None


class UserProfileStore:
    """Persist/retrieve lightweight Telegram runtime profile in users.preferences."""

    def __init__(self, default_timezone: str | None = None) -> None:
        self._default_timezone = _safe_timezone_name(default_timezone or os.getenv("USER_TIMEZONE", "UTC"))

    def get_profile(self, user_id: int | str) -> RuntimeUserProfile:
        user_key = str(user_id).strip()
        if not user_key:
            return RuntimeUserProfile(user_id="", chat_id=None, timezone=self._default_timezone, telegram_user_id=None)

        connection = None
        try:
            import psycopg2

            connection = psycopg2.connect(
                dbname=os.getenv("POSTGRES_DB", "her_memory"),
                user=os.getenv("POSTGRES_USER", "her"),
                password=os.getenv("POSTGRES_PASSWORD", ""),
                host=os.getenv("POSTGRES_HOST", "postgres"),
                port=int(os.getenv("POSTGRES_PORT", "5432")),
            )
            with connection, connection.cursor() as cursor:
                cursor.execute("SELECT preferences FROM users WHERE user_id = %s", (user_key,))
                row = cursor.fetchone()
                preferences = row[0] if row and isinstance(row[0], dict) else {}
                chat_id_raw = preferences.get("chat_id")
                telegram_user_id_raw = preferences.get("telegram_user_id")
                timezone_name = _safe_timezone_name(str(preferences.get("user_timezone", self._default_timezone)))
                return RuntimeUserProfile(
                    user_id=user_key,
                    chat_id=int(chat_id_raw) if str(chat_id_raw).isdigit() else None,
                    timezone=timezone_name,
                    telegram_user_id=int(telegram_user_id_raw) if str(telegram_user_id_raw).isdigit() else None,
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("User profile lookup failed for user %s: %s", user_key, exc)
            return RuntimeUserProfile(
                user_id=user_key,
                chat_id=None,
                timezone=self._default_timezone,
                telegram_user_id=int(user_key) if user_key.isdigit() else None,
            )
        finally:
            if connection is not None:
                connection.close()

    def persist_telegram_identity(
        self,
        *,
        user_id: int,
        chat_id: int,
        username: str | None = None,
        timezone_name: str | None = None,
    ) -> RuntimeUserProfile:
        user_key = str(user_id)
        resolved_tz = _safe_timezone_name(timezone_name or self._default_timezone)
        payload = {
            "telegram_user_id": int(user_id),
            "chat_id": int(chat_id),
            "user_timezone": resolved_tz,
        }

        connection = None
        try:
            import psycopg2

            connection = psycopg2.connect(
                dbname=os.getenv("POSTGRES_DB", "her_memory"),
                user=os.getenv("POSTGRES_USER", "her"),
                password=os.getenv("POSTGRES_PASSWORD", ""),
                host=os.getenv("POSTGRES_HOST", "postgres"),
                port=int(os.getenv("POSTGRES_PORT", "5432")),
            )
            with connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO users (user_id, username, last_interaction, preferences)
                    VALUES (%s, %s, NOW(), %s::jsonb)
                    ON CONFLICT (user_id)
                    DO UPDATE SET
                        username = COALESCE(EXCLUDED.username, users.username),
                        last_interaction = NOW(),
                        preferences = COALESCE(users.preferences, '{}'::jsonb) || EXCLUDED.preferences
                    """,
                    (user_key, (username or "").strip() or None, json.dumps(payload)),
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to persist Telegram identity for user %s: %s", user_key, exc)
        finally:
            if connection is not None:
                connection.close()

        return RuntimeUserProfile(
            user_id=user_key,
            chat_id=int(chat_id),
            timezone=resolved_tz,
            telegram_user_id=int(user_id),
        )

    def resolve_user_timezone(self, user_id: int | str) -> str:
        return self.get_profile(user_id).timezone

    def resolve_chat_id(self, user_id: int | str) -> int | None:
        return self.get_profile(user_id).chat_id

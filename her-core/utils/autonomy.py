from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from models.autonomy_profile import AutonomyProfile, EmotionalState, ReflectionEntry
from utils.decision_log import DecisionLogger

logger = logging.getLogger(__name__)

_POSITIVE_PATTERN = re.compile(r"\b(thanks|great|good|awesome|perfect|helpful|merci|دمت گرم|عالی|ممنون)\b", re.IGNORECASE)
_COLD_PATTERN = re.compile(r"^(ok|k|fine|sure|نه|باشه|اوکی)\W*$", re.IGNORECASE)
_DISABLE_PATTERN = re.compile(r"(mute|stop proactive|disable proactive|خاموش|مزاحم نشو|پیام نده)", re.IGNORECASE)
_STRESS_PATTERN = re.compile(r"\b(stress|stressed|overwhelmed|anxious|deadline|burnout|استرس|ددلاین|فشار)\b", re.IGNORECASE)

_MOOD_ORDER = ["calm", "reflective", "supportive", "curious", "playful"]


class AutonomyService:
    """Persistence + control logic for bounded semi-autonomous behavior."""

    def __init__(self) -> None:
        self._decision_logger = DecisionLogger()

    @staticmethod
    def _connect() -> Any:
        import psycopg2

        return psycopg2.connect(
            dbname=os.getenv("POSTGRES_DB", "her_memory"),
            user=os.getenv("POSTGRES_USER", "her"),
            password=os.getenv("POSTGRES_PASSWORD", ""),
            host=os.getenv("POSTGRES_HOST", "postgres"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
        )

    def ensure_tables(self) -> None:
        connection = None
        try:
            connection = self._connect()
            with connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS autonomy_profiles (
                        user_id TEXT PRIMARY KEY,
                        engagement_score DOUBLE PRECISION NOT NULL DEFAULT 0.5,
                        initiative_level DOUBLE PRECISION NOT NULL DEFAULT 0.5,
                        last_proactive_at TIMESTAMPTZ,
                        messages_sent_today INTEGER NOT NULL DEFAULT 0,
                        proactive_day DATE,
                        error_count_today INTEGER NOT NULL DEFAULT 0,
                        last_user_message_at TIMESTAMPTZ,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        CONSTRAINT autonomy_profiles_engagement_bounds CHECK (engagement_score >= 0.1 AND engagement_score <= 1.0),
                        CONSTRAINT autonomy_profiles_initiative_bounds CHECK (initiative_level >= 0.1 AND initiative_level <= 1.0)
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS emotional_states (
                        user_id TEXT PRIMARY KEY,
                        current_mood TEXT NOT NULL DEFAULT 'calm',
                        mood_intensity DOUBLE PRECISION NOT NULL DEFAULT 0.5,
                        last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        shift_date DATE,
                        shifts_today INTEGER NOT NULL DEFAULT 0,
                        CONSTRAINT emotional_states_intensity_bounds CHECK (mood_intensity >= 0.1 AND mood_intensity <= 1.0)
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS autonomy_reflections (
                        reflection_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id TEXT NOT NULL,
                        reflection_date DATE NOT NULL,
                        engagement_trend TEXT NOT NULL,
                        initiative_adjustment DOUBLE PRECISION NOT NULL,
                        notes TEXT NOT NULL,
                        confidence TEXT NOT NULL DEFAULT 'medium',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        UNIQUE(user_id, reflection_date)
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS proactive_daily_slots (
                        user_id TEXT NOT NULL,
                        day_bucket DATE NOT NULL,
                        slot SMALLINT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (user_id, day_bucket, slot),
                        CONSTRAINT proactive_daily_slot_range CHECK (slot >= 1 AND slot <= 3)
                    )
                    """
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("autonomy_tables_init_failed", extra={"event": "autonomy_tables_init_failed", "error": str(exc)})
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _clamp(value: float, low: float = 0.1, high: float = 1.0) -> float:
        return max(low, min(high, value))

    @staticmethod
    def _parse_dt(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:  # noqa: BLE001
            return None

    def _upsert_profile(self, user_id: str) -> None:
        connection = None
        try:
            connection = self._connect()
            with connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO autonomy_profiles (user_id)
                    VALUES (%s)
                    ON CONFLICT (user_id) DO NOTHING
                    """,
                    (str(user_id),),
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("autonomy_profile_upsert_failed for %s: %s", user_id, exc)
        finally:
            if connection is not None:
                connection.close()

    def _upsert_emotion(self, user_id: str) -> None:
        connection = None
        try:
            connection = self._connect()
            with connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO emotional_states (user_id)
                    VALUES (%s)
                    ON CONFLICT (user_id) DO NOTHING
                    """,
                    (str(user_id),),
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("emotional_state_upsert_failed for %s: %s", user_id, exc)
        finally:
            if connection is not None:
                connection.close()

    def get_profile(self, user_id: str) -> AutonomyProfile:
        self._upsert_profile(user_id)
        connection = None
        try:
            connection = self._connect()
            with connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT user_id, engagement_score, initiative_level, last_proactive_at,
                           messages_sent_today, proactive_day, error_count_today, last_user_message_at
                    FROM autonomy_profiles
                    WHERE user_id = %s
                    """,
                    (str(user_id),),
                )
                row = cursor.fetchone()
                if not row:
                    return AutonomyProfile(user_id=str(user_id))
                return AutonomyProfile(
                    user_id=str(row[0]),
                    engagement_score=float(row[1] or 0.5),
                    initiative_level=float(row[2] or 0.5),
                    last_proactive_at=self._parse_dt(row[3]),
                    messages_sent_today=int(row[4] or 0),
                    proactive_day=datetime.combine(row[5], time.min, tzinfo=timezone.utc) if row[5] else None,
                    error_count_today=int(row[6] or 0),
                    last_user_message_at=self._parse_dt(row[7]),
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("autonomy_profile_lookup_failed for %s: %s", user_id, exc)
            return AutonomyProfile(user_id=str(user_id))
        finally:
            if connection is not None:
                connection.close()

    def get_emotional_state(self, user_id: str) -> EmotionalState:
        self._upsert_emotion(user_id)
        connection = None
        try:
            connection = self._connect()
            with connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT user_id, current_mood, mood_intensity, last_updated, shift_date, shifts_today
                    FROM emotional_states
                    WHERE user_id = %s
                    """,
                    (str(user_id),),
                )
                row = cursor.fetchone()
                if not row:
                    return EmotionalState(user_id=str(user_id))
                return EmotionalState(
                    user_id=str(row[0]),
                    current_mood=str(row[1] or "calm"),
                    mood_intensity=float(row[2] or 0.5),
                    last_updated=self._parse_dt(row[3]),
                    shift_date=datetime.combine(row[4], time.min, tzinfo=timezone.utc) if row[4] else None,
                    shifts_today=int(row[5] or 0),
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("emotional_state_lookup_failed for %s: %s", user_id, exc)
            return EmotionalState(user_id=str(user_id))
        finally:
            if connection is not None:
                connection.close()

    def _write_profile(self, profile: AutonomyProfile) -> None:
        connection = None
        try:
            today = datetime.now(timezone.utc).date()
            stored_day = profile.proactive_day.date() if profile.proactive_day else None
            if stored_day != today:
                profile.messages_sent_today = 0
                profile.error_count_today = 0
                profile.proactive_day = datetime.combine(today, time.min, tzinfo=timezone.utc)

            connection = self._connect()
            with connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO autonomy_profiles (
                        user_id, engagement_score, initiative_level, last_proactive_at,
                        messages_sent_today, proactive_day, error_count_today, last_user_message_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (user_id)
                    DO UPDATE SET
                        engagement_score = EXCLUDED.engagement_score,
                        initiative_level = EXCLUDED.initiative_level,
                        last_proactive_at = EXCLUDED.last_proactive_at,
                        messages_sent_today = EXCLUDED.messages_sent_today,
                        proactive_day = EXCLUDED.proactive_day,
                        error_count_today = EXCLUDED.error_count_today,
                        last_user_message_at = EXCLUDED.last_user_message_at,
                        updated_at = NOW()
                    """,
                    (
                        profile.user_id,
                        self._clamp(profile.engagement_score),
                        self._clamp(profile.initiative_level),
                        profile.last_proactive_at,
                        max(0, int(profile.messages_sent_today)),
                        profile.proactive_day.date() if profile.proactive_day else datetime.now(timezone.utc).date(),
                        max(0, int(profile.error_count_today)),
                        profile.last_user_message_at,
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("autonomy_profile_write_failed for %s: %s", profile.user_id, exc)
        finally:
            if connection is not None:
                connection.close()

    def _write_emotion(self, state: EmotionalState) -> None:
        connection = None
        try:
            connection = self._connect()
            with connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO emotional_states (user_id, current_mood, mood_intensity, last_updated, shift_date, shifts_today)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id)
                    DO UPDATE SET
                        current_mood = EXCLUDED.current_mood,
                        mood_intensity = EXCLUDED.mood_intensity,
                        last_updated = EXCLUDED.last_updated,
                        shift_date = EXCLUDED.shift_date,
                        shifts_today = EXCLUDED.shifts_today
                    """,
                    (
                        state.user_id,
                        state.current_mood,
                        self._clamp(state.mood_intensity),
                        state.last_updated or datetime.now(timezone.utc),
                        state.shift_date.date() if state.shift_date else datetime.now(timezone.utc).date(),
                        max(0, int(state.shifts_today)),
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("emotional_state_write_failed for %s: %s", state.user_id, exc)
        finally:
            if connection is not None:
                connection.close()

    def record_user_message(
        self,
        *,
        user_id: str,
        message: str,
        user_initiated: bool,
        response_seconds: float | None,
    ) -> dict[str, Any]:
        profile = self.get_profile(user_id)
        now = datetime.now(timezone.utc)

        message_text = str(message or "").strip()
        message_length = len(message_text)
        positive = bool(_POSITIVE_PATTERN.search(message_text))
        cold = message_length < 12 or bool(_COLD_PATTERN.match(message_text))
        disabled = bool(_DISABLE_PATTERN.search(message_text))
        stress = bool(_STRESS_PATTERN.search(message_text))
        ignored = response_seconds is not None and response_seconds >= 6 * 3600

        delta = 0.0
        if response_seconds is not None:
            if response_seconds <= 120:
                delta += 0.08
            elif response_seconds <= 600:
                delta += 0.05
            elif response_seconds >= 21600:
                delta -= 0.08
        if message_length >= 280:
            delta += 0.06
        elif message_length >= 120:
            delta += 0.03
        elif message_length <= 20:
            delta -= 0.03
        if user_initiated:
            delta += 0.04
        if positive:
            delta += 0.05
        if ignored:
            delta -= 0.07
        if cold:
            delta -= 0.05
        if disabled:
            delta -= 0.2

        profile.engagement_score = self._clamp(profile.engagement_score + delta)
        target_initiative = self._clamp((profile.engagement_score * 0.75) + 0.2)
        profile.initiative_level = self._clamp((profile.initiative_level * 0.75) + (target_initiative * 0.25))
        profile.last_user_message_at = now
        self._write_profile(profile)

        emotion = self.get_emotional_state(user_id)
        self._apply_mood_update(emotion, engagement=profile.engagement_score, stress=stress, positive=positive)
        self._write_emotion(emotion)

        details = {
            "engagement_score": round(profile.engagement_score, 3),
            "initiative_level": round(profile.initiative_level, 3),
            "positive": positive,
            "cold": cold,
            "disabled": disabled,
            "ignored": ignored,
            "response_seconds": round(response_seconds, 2) if response_seconds is not None else None,
            "mood": emotion.current_mood,
            "mood_intensity": round(emotion.mood_intensity, 3),
        }
        self._decision_logger.log(
            event_type="autonomy_profile_updated",
            summary=f"Autonomy profile updated for user {user_id}",
            user_id=str(user_id),
            source="autonomy",
            details=details,
        )
        return {
            "profile": asdict(profile),
            "emotion": asdict(emotion),
            "disabled": disabled,
            "positive": positive,
            "stress": stress,
        }

    def _apply_mood_update(self, emotion: EmotionalState, *, engagement: float, stress: bool, positive: bool) -> None:
        now = datetime.now(timezone.utc)
        current = emotion.current_mood if emotion.current_mood in _MOOD_ORDER else "calm"
        local_hour = now.hour

        desired = "calm"
        if stress:
            desired = "supportive"
        elif positive and engagement >= 0.75:
            desired = "playful"
        elif engagement >= 0.7:
            desired = "curious"
        elif local_hour >= 20:
            desired = "reflective"
        elif 5 <= local_hour < 10:
            desired = "curious"
        elif engagement >= 0.5:
            desired = "supportive"

        shift_date = emotion.shift_date.date() if emotion.shift_date else None
        today = now.date()
        shifts_today = int(emotion.shifts_today or 0)
        if shift_date != today:
            shifts_today = 0

        current_idx = _MOOD_ORDER.index(current)
        desired_idx = _MOOD_ORDER.index(desired)
        if current_idx != desired_idx and shifts_today < 1:
            if desired_idx > current_idx:
                current_idx += 1
            else:
                current_idx -= 1
            shifts_today += 1

        emotion.current_mood = _MOOD_ORDER[current_idx]
        target_intensity = self._clamp(0.35 + (engagement * 0.5))
        if stress:
            target_intensity = max(target_intensity, 0.65)
        # Slow decay and bounded adjustment; avoids abrupt personality shifts.
        emotion.mood_intensity = self._clamp((emotion.mood_intensity * 0.82) + (target_intensity * 0.18))
        emotion.last_updated = now
        emotion.shift_date = datetime.combine(today, time.min, tzinfo=timezone.utc)
        emotion.shifts_today = shifts_today

    def daily_proactive_target(self, user_id: str) -> int:
        profile = self.get_profile(user_id)
        engagement = profile.engagement_score
        if engagement < 0.2:
            return 0
        if engagement < 0.3:
            base = 1
        elif engagement < 0.6:
            base = 1
        elif engagement < 0.8:
            base = 2
        else:
            base = 3
        scaled = int(round(base * (0.65 + (0.5 * profile.initiative_level))))
        return max(0, min(3, scaled))

    def can_send_proactive(
        self,
        *,
        user_id: str,
        timezone_name: str,
        quiet_hours_start: int = 22,
        quiet_hours_end: int = 8,
    ) -> tuple[bool, str, dict[str, Any]]:
        profile = self.get_profile(user_id)
        emotion = self.get_emotional_state(user_id)
        now = datetime.now(timezone.utc)
        if profile.engagement_score < 0.2:
            return False, "low_engagement", {"profile": asdict(profile), "emotion": asdict(emotion)}

        day = now.date()
        profile_day = profile.proactive_day.date() if profile.proactive_day else day
        sent_today = profile.messages_sent_today if profile_day == day else 0
        target = self.daily_proactive_target(user_id)
        if sent_today >= min(target, 3):
            return False, "daily_target_reached", {"profile": asdict(profile), "emotion": asdict(emotion), "target": target}
        if sent_today >= 3:
            return False, "hard_daily_cap", {"profile": asdict(profile), "emotion": asdict(emotion), "target": target}

        if profile.last_proactive_at and (now - profile.last_proactive_at) < timedelta(hours=2):
            return False, "cooldown_active", {"profile": asdict(profile), "emotion": asdict(emotion), "target": target}

        try:
            tz = ZoneInfo(str(timezone_name).strip() or "UTC")
        except Exception:  # noqa: BLE001
            tz = ZoneInfo("UTC")
        local_hour = now.astimezone(tz).hour
        in_quiet_hours = local_hour >= int(quiet_hours_start) or local_hour < int(quiet_hours_end)
        if in_quiet_hours:
            return False, "quiet_hours", {"profile": asdict(profile), "emotion": asdict(emotion), "target": target}

        return True, "ok", {"profile": asdict(profile), "emotion": asdict(emotion), "target": target}

    def reserve_daily_slot(self, user_id: str, day_bucket: date) -> int | None:
        connection = None
        try:
            connection = self._connect()
            with connection, connection.cursor() as cursor:
                for slot in (1, 2, 3):
                    cursor.execute(
                        """
                        INSERT INTO proactive_daily_slots (user_id, day_bucket, slot)
                        VALUES (%s, %s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (str(user_id), day_bucket, slot),
                    )
                    if cursor.rowcount == 1:
                        return slot
        except Exception as exc:  # noqa: BLE001
            logger.debug("reserve_daily_slot_failed for %s: %s", user_id, exc)
            return None
        finally:
            if connection is not None:
                connection.close()
        return None

    def register_proactive_result(self, user_id: str, *, sent: bool, error: str = "") -> dict[str, Any]:
        profile = self.get_profile(user_id)
        now = datetime.now(timezone.utc)
        day = now.date()
        profile_day = profile.proactive_day.date() if profile.proactive_day else day
        if profile_day != day:
            profile.messages_sent_today = 0
            profile.error_count_today = 0

        if sent:
            profile.messages_sent_today = min(3, int(profile.messages_sent_today) + 1)
            profile.last_proactive_at = now
            profile.error_count_today = 0
        else:
            profile.error_count_today = int(profile.error_count_today) + 1
            if profile.error_count_today >= 3:
                profile.initiative_level = self._clamp(profile.initiative_level - 0.12)

        profile.proactive_day = datetime.combine(day, time.min, tzinfo=timezone.utc)
        self._write_profile(profile)

        self._decision_logger.log(
            event_type="proactive_outcome",
            summary=f"Proactive outcome recorded for user {user_id}",
            user_id=str(user_id),
            source="autonomy",
            details={
                "sent": sent,
                "error": error,
                "messages_sent_today": profile.messages_sent_today,
                "error_count_today": profile.error_count_today,
                "initiative_level": round(profile.initiative_level, 3),
            },
        )
        return asdict(profile)

    def generate_daily_reflection(self, user_id: str, target_day: date) -> ReflectionEntry:
        profile = self.get_profile(user_id)
        connection = None
        sent = 0
        failed = 0
        ignored = 0
        try:
            connection = self._connect()
            with connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE success = TRUE),
                        COUNT(*) FILTER (WHERE success = FALSE),
                        COUNT(*) FILTER (WHERE details::text ILIKE '%ignored%')
                    FROM proactive_message_audit
                    WHERE user_id = %s
                      AND COALESCE(day_bucket, DATE(scheduled_at)) = %s
                    """,
                    (str(user_id), target_day),
                )
                row = cursor.fetchone() or (0, 0, 0)
                sent = int(row[0] or 0)
                failed = int(row[1] or 0)
                ignored = int(row[2] or 0)
        except Exception as exc:  # noqa: BLE001
            logger.debug("reflection_metrics_query_failed for %s: %s", user_id, exc)
        finally:
            if connection is not None:
                connection.close()

        trend = "stable"
        initiative_adjustment = 0.0
        note = "Engagement steady."

        target = self.daily_proactive_target(user_id)
        if sent > target and sent >= 2:
            trend = "over_initiating"
            initiative_adjustment = -0.12
            note = "Proactive volume felt high; reducing initiative."
        elif sent == 0 and profile.engagement_score >= 0.45:
            trend = "under_engaged"
            initiative_adjustment = 0.08
            note = "Low outreach despite moderate engagement; increasing curiosity prompts."
        elif ignored >= 1 or failed >= 2:
            trend = "friction"
            initiative_adjustment = -0.08
            note = "User seemed distant or delivery had friction."

        profile.initiative_level = self._clamp(profile.initiative_level + initiative_adjustment)
        profile.engagement_score = self._clamp(profile.engagement_score - 0.02)  # slow daily decay
        self._write_profile(profile)

        if _STRESS_PATTERN.search(note):
            emotion = self.get_emotional_state(user_id)
            emotion.current_mood = "supportive"
            emotion.mood_intensity = self._clamp(max(emotion.mood_intensity, 0.65))
            self._write_emotion(emotion)

        entry = ReflectionEntry(
            user_id=str(user_id),
            date=target_day.isoformat(),
            engagement_trend=trend,
            initiative_adjustment=round(initiative_adjustment, 3),
            notes=note,
        )

        connection = None
        try:
            connection = self._connect()
            with connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO autonomy_reflections (
                        user_id, reflection_date, engagement_trend, initiative_adjustment, notes, confidence
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, reflection_date)
                    DO UPDATE SET
                        engagement_trend = EXCLUDED.engagement_trend,
                        initiative_adjustment = EXCLUDED.initiative_adjustment,
                        notes = EXCLUDED.notes,
                        confidence = EXCLUDED.confidence,
                        created_at = NOW()
                    """,
                    (
                        entry.user_id,
                        target_day,
                        entry.engagement_trend,
                        entry.initiative_adjustment,
                        entry.notes,
                        entry.confidence,
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("reflection_write_failed for %s: %s", user_id, exc)
        finally:
            if connection is not None:
                connection.close()

        self._decision_logger.log(
            event_type="reflection",
            summary=f"Daily reflection generated for user {user_id}",
            user_id=str(user_id),
            source="scheduler",
            details={
                "event": "reflection",
                "date": entry.date,
                "engagement_trend": entry.engagement_trend,
                "initiative_adjustment": entry.initiative_adjustment,
                "notes": entry.notes,
                "confidence": entry.confidence,
            },
        )
        return entry

    def profile_snapshot(self, user_id: str) -> dict[str, Any]:
        profile = self.get_profile(user_id)
        emotion = self.get_emotional_state(user_id)
        return {
            "user_id": str(user_id),
            "engagement_score": round(profile.engagement_score, 3),
            "initiative_level": round(profile.initiative_level, 3),
            "messages_sent_today": int(profile.messages_sent_today),
            "last_proactive_at": profile.last_proactive_at.isoformat() if profile.last_proactive_at else "",
            "current_mood": emotion.current_mood,
            "mood_intensity": round(emotion.mood_intensity, 3),
            "daily_target": self.daily_proactive_target(user_id),
        }

    @staticmethod
    def parse_signal_flags(message: str) -> dict[str, bool]:
        text = str(message or "")
        return {
            "positive": bool(_POSITIVE_PATTERN.search(text)),
            "cold": len(text.strip()) < 12 or bool(_COLD_PATTERN.match(text.strip())),
            "disabled": bool(_DISABLE_PATTERN.search(text)),
            "stress": bool(_STRESS_PATTERN.search(text)),
        }

    def serialize_reflection(self, entry: ReflectionEntry) -> str:
        return json.dumps(
            {
                "date": entry.date,
                "engagement_trend": entry.engagement_trend,
                "initiative_adjustment": entry.initiative_adjustment,
                "notes": entry.notes,
                "confidence": entry.confidence,
            },
            ensure_ascii=True,
        )

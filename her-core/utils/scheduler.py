"""Persistent APScheduler runtime for HER.

Scheduler rules:
- No cron daemon and no sleep polling loops.
- All recurring work is registered as APScheduler jobs.
- Jobs survive restart via SQLAlchemyJobStore.
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import threading
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import yaml
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from agents.personality_agent import PersonalityAgent
from utils.config_paths import resolve_config_file
from utils.decision_log import DecisionLogger
from utils.reinforcement import ReinforcementEngine
from utils.schedule_helpers import normalize_weekdays_input
from utils.user_profiles import UserProfileStore

logger = logging.getLogger(__name__)
_TERMINAL_REMINDER_STATES = {"SENT", "FAILED"}


@dataclass
class _LockHandle:
    connection: Any


class TaskScheduler:
    """APScheduler-backed persistent task scheduler."""

    def __init__(self) -> None:
        self.tasks: list[dict[str, Any]] = []
        self.running = False
        self._config_path: Path | None = None
        self._decision_logger = DecisionLogger()
        self._reinforcement = ReinforcementEngine()
        self._user_profiles = UserProfileStore(default_timezone=os.getenv("USER_TIMEZONE", "UTC"))
        self._start_lock = threading.Lock()
        self._scheduler: BackgroundScheduler | None = None
        self._jobstores = {
            "default": SQLAlchemyJobStore(url=self._scheduler_db_url()),
        }

    async def start(self) -> None:
        with self._start_lock:
            if self.running:
                logger.info("scheduler_start_skipped", extra={"event": "scheduler_start_skipped", "reason": "already_running"})
                return
            self._load_tasks()
            self._ensure_baseline_tasks()
            self._scheduler = BackgroundScheduler(jobstores=self._jobstores, timezone=self._system_timezone())
            self._scheduler.start()
            self._ensure_lock_table()
            self._register_system_jobs()
            self._sync_all_task_jobs()
            self.running = True
            self._publish_scheduler_state()
            logger.info(
                "scheduler_started",
                extra={
                    "event": "scheduler_started",
                    "task_count": len(self.tasks),
                    "timezone": self._system_timezone(),
                    "db_url": self._scheduler_db_url(redacted=True),
                },
            )

    async def stop(self) -> None:
        with self._start_lock:
            if not self.running:
                return
            if self._scheduler is not None:
                self._scheduler.shutdown(wait=False)
            self.running = False
            self._publish_scheduler_state()
            logger.info("scheduler_stopped", extra={"event": "scheduler_stopped"})

    @staticmethod
    def _scheduler_db_url(redacted: bool = False) -> str:
        configured = os.getenv("SCHEDULER_DATABASE_URL", "").strip()
        if configured:
            if redacted:
                return re.sub(r"://([^:/]+):([^@]+)@", r"://\\1:***@", configured)
            return configured
        dsn = (
            f"postgresql+psycopg2://{os.getenv('POSTGRES_USER', 'her')}:{os.getenv('POSTGRES_PASSWORD', '')}"
            f"@{os.getenv('POSTGRES_HOST', 'postgres')}:{int(os.getenv('POSTGRES_PORT', '5432'))}"
            f"/{os.getenv('POSTGRES_DB', 'her_memory')}"
        )
        if redacted:
            return re.sub(r"://([^:/]+):([^@]+)@", r"://\\1:***@", dsn)
        return dsn

    @staticmethod
    def _system_timezone() -> str:
        candidate = (os.getenv("TZ", "UTC") or "UTC").strip() or "UTC"
        try:
            ZoneInfo(candidate)
            return candidate
        except Exception:  # noqa: BLE001
            return "UTC"

    def _ensure_lock_table(self) -> None:
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
                    CREATE TABLE IF NOT EXISTS scheduler_job_locks (
                        lock_name TEXT PRIMARY KEY,
                        holder TEXT,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("scheduler_lock_table_init_failed", extra={"event": "scheduler_lock_table_init_failed", "error": str(exc)})
        finally:
            if connection is not None:
                connection.close()

    def _acquire_job_lock(self, lock_name: str) -> _LockHandle | None:
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
            connection.autocommit = False
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO scheduler_job_locks (lock_name, holder, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (lock_name)
                    DO NOTHING
                    """,
                    (lock_name, os.getenv("HOSTNAME", "unknown")),
                )
                cursor.execute(
                    """
                    SELECT lock_name
                    FROM scheduler_job_locks
                    WHERE lock_name = %s
                    FOR UPDATE SKIP LOCKED
                    """,
                    (lock_name,),
                )
                row = cursor.fetchone()
                if not row:
                    connection.rollback()
                    connection.close()
                    return None
                cursor.execute(
                    "UPDATE scheduler_job_locks SET holder=%s, updated_at=NOW() WHERE lock_name=%s",
                    (os.getenv("HOSTNAME", "unknown"), lock_name),
                )
            return _LockHandle(connection=connection)
        except Exception as exc:  # noqa: BLE001
            if connection is not None:
                try:
                    connection.rollback()
                    connection.close()
                except Exception:  # noqa: BLE001
                    pass
            logger.warning("scheduler_lock_acquire_failed", extra={"event": "scheduler_lock_acquire_failed", "lock_name": lock_name, "error": str(exc)})
            return None

    @staticmethod
    def _release_job_lock(handle: _LockHandle | None) -> None:
        if handle is None:
            return
        try:
            handle.connection.commit()
        except Exception:  # noqa: BLE001
            try:
                handle.connection.rollback()
            except Exception:  # noqa: BLE001
                pass
        finally:
            try:
                handle.connection.close()
            except Exception:  # noqa: BLE001
                pass

    def _load_tasks(self) -> None:
        try:
            config_path = resolve_config_file("scheduler.yaml")
            self._config_path = config_path
            if not config_path.exists():
                self.tasks = []
                return
            with config_path.open("r", encoding="utf-8") as handle:
                config = yaml.safe_load(handle) or {}
            loaded: list[dict[str, Any]] = []
            for raw_task in config.get("tasks", []):
                task = self._normalize_task(raw_task)
                if task is not None:
                    loaded.append(task)
            self.tasks = loaded
            logger.info("scheduler_tasks_loaded", extra={"event": "scheduler_tasks_loaded", "count": len(self.tasks)})
        except Exception as exc:  # noqa: BLE001
            logger.warning("scheduler_tasks_load_failed", extra={"event": "scheduler_tasks_load_failed", "error": str(exc)})
            self.tasks = []

    def _ensure_baseline_tasks(self) -> None:
        baseline = [
            {
                "name": "memory_reflection",
                "type": "memory_reflection",
                "interval": "hourly",
                "enabled": True,
                "max_retries": 2,
                "retry_delay_seconds": 30,
            },
            {
                "name": "weekly_self_optimization",
                "type": "self_optimization",
                "interval": "weekly",
                "enabled": True,
                "at": "18:00",
                "timezone": self._system_timezone(),
                "max_retries": 1,
                "retry_delay_seconds": 60,
            },
            {
                "name": "proactive_daily_dispatcher",
                "type": "proactive_daily_dispatcher",
                "interval": "daily",
                "enabled": True,
                "at": "08:05",
                "timezone": self._system_timezone(),
                "max_retries": 1,
                "retry_delay_seconds": 60,
            },
        ]
        by_name = {str(task.get("name", "")): task for task in self.tasks}
        for item in baseline:
            existing = by_name.get(item["name"])
            if existing is None:
                self.tasks.append(item)
                continue
            existing["enabled"] = True
            existing["interval"] = item["interval"]
            existing["type"] = item["type"]
            if item.get("at"):
                existing["at"] = item["at"]
            if item.get("timezone"):
                existing["timezone"] = item["timezone"]
            existing.setdefault("max_retries", item["max_retries"])
            existing.setdefault("retry_delay_seconds", item["retry_delay_seconds"])

    def _register_system_jobs(self) -> None:
        if self._scheduler is None:
            return
        self._scheduler.add_job(
            func=self._run_system_reminder_processor,
            trigger=IntervalTrigger(minutes=1, timezone=self._system_timezone()),
            id="system:reminder_processor",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=60,
        )
        self._scheduler.add_job(
            func=self._run_follow_up_logic,
            trigger=IntervalTrigger(minutes=30, timezone=self._system_timezone()),
            id="system:follow_up_logic",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=120,
        )

    def _sync_all_task_jobs(self) -> None:
        if self._scheduler is None:
            return
        for task in self.tasks:
            self._upsert_task_job(task)
        self._publish_scheduler_state()

    def _upsert_task_job(self, task: dict[str, Any]) -> None:
        if self._scheduler is None:
            return
        name = str(task.get("name", "")).strip()
        if not name:
            return
        job_id = f"task:{name}"
        if not bool(task.get("enabled", True)):
            try:
                self._scheduler.remove_job(job_id)
            except Exception:  # noqa: BLE001
                pass
            return

        trigger = self._build_trigger(task)
        if trigger is None:
            logger.warning("scheduler_invalid_trigger", extra={"event": "scheduler_invalid_trigger", "task": name})
            return

        self._scheduler.add_job(
            func=self._run_task_job,
            trigger=trigger,
            id=job_id,
            replace_existing=True,
            kwargs={"task_name": name},
            max_instances=1,
            coalesce=True,
            misfire_grace_time=120,
        )

    @staticmethod
    def is_valid_interval(interval: str) -> bool:
        value = str(interval or "").strip().lower()
        if value in {"once", "hourly", "daily", "weekly"}:
            return True
        if value.startswith("every_"):
            parts = value.split("_")
            return len(parts) == 3 and parts[1].isdigit() and parts[2] in {"minutes", "hours", "days"}
        return False

    @staticmethod
    def _parse_clock(at_value: str) -> tuple[int, int] | None:
        match = re.match(r"^(\d{2}):(\d{2})$", str(at_value).strip())
        if not match:
            return None
        hour, minute = int(match.group(1)), int(match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
        return None

    def _build_trigger(self, task: dict[str, Any]) -> Any | None:
        interval = str(task.get("interval", "")).strip().lower()
        timezone_name = str(task.get("timezone", self._system_timezone())).strip() or self._system_timezone()
        try:
            ZoneInfo(timezone_name)
        except Exception:  # noqa: BLE001
            timezone_name = "UTC"

        if interval == "once":
            run_at = self._parse_iso_timestamp(task.get("run_at"))
            if run_at is None:
                return None
            return DateTrigger(run_date=run_at)
        if interval == "hourly":
            return IntervalTrigger(hours=1, timezone=timezone_name)
        if interval.startswith("every_"):
            _, count_text, unit = interval.split("_", 2)
            count = max(1, int(count_text))
            if unit == "minutes":
                return IntervalTrigger(minutes=count, timezone=timezone_name)
            if unit == "hours":
                return IntervalTrigger(hours=count, timezone=timezone_name)
            if unit == "days":
                return IntervalTrigger(days=count, timezone=timezone_name)
            return None

        at_parsed = self._parse_clock(str(task.get("at", "")))
        weekdays = normalize_weekdays_input(task.get("weekdays"))
        if interval == "daily":
            if at_parsed is None:
                return IntervalTrigger(days=1, timezone=timezone_name)
            hour, minute = at_parsed
            day_of_week = ",".join(str(item) for item in weekdays) if weekdays else "*"
            return CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute, timezone=timezone_name)
        if interval == "weekly":
            if at_parsed is None:
                at_parsed = (9, 0)
            hour, minute = at_parsed
            if not weekdays:
                weekdays = [0]
            day_of_week = ",".join(str(item) for item in weekdays)
            return CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute, timezone=timezone_name)
        return None

    @staticmethod
    def _parse_iso_timestamp(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            raw = str(value)
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:  # noqa: BLE001
            return None

    def _find_task(self, task_name: str) -> dict[str, Any] | None:
        for task in self.tasks:
            if str(task.get("name", "")).strip() == task_name:
                return task
        return None

    def _run_task_job(self, task_name: str) -> None:
        task = self._find_task(task_name)
        if task is None:
            return
        lock_name = f"task:{task_name}"
        lock = self._acquire_job_lock(lock_name)
        if lock is None:
            logger.info("scheduler_task_skipped_locked", extra={"event": "scheduler_task_skipped_locked", "task": task_name})
            return
        try:
            started = time.perf_counter()
            success, result, error = self._execute_task(task)
            task["_last_run"] = datetime.now(timezone.utc).isoformat()
            if bool(task.get("one_time", str(task.get("interval", "")).lower() == "once")) and success:
                task["enabled"] = False
                self._upsert_task_job(task)
            self._log_job_execution(
                name=task_name,
                job_type=str(task.get("type", "custom")),
                success=success,
                result=result,
                error=error,
                execution_time=time.perf_counter() - started,
                next_run=self._next_run_for_task(task_name),
            )
            self._publish_scheduler_state()
        finally:
            self._release_job_lock(lock)

    def _run_system_reminder_processor(self) -> None:
        lock = self._acquire_job_lock("system:reminder_processor")
        if lock is None:
            return
        try:
            now = datetime.now(timezone.utc).isoformat()
            self._decision_logger.log(
                event_type="scheduler_system_job",
                summary="Reminder processor heartbeat",
                source="scheduler",
                details={"job": "reminder_processor", "timestamp": now},
            )
        finally:
            self._release_job_lock(lock)

    def _run_follow_up_logic(self) -> None:
        lock = self._acquire_job_lock("system:follow_up_logic")
        if lock is None:
            return
        try:
            now = datetime.now(timezone.utc)
            for profile in self._active_user_profiles(limit=500):
                if profile.proactive_opt_out:
                    continue
                if not profile.chat_id:
                    continue
                if self._has_recent_proactive_send(profile.user_id, within_hours=18):
                    continue
                last_touch = self._last_user_context_timestamp(profile.user_id)
                if last_touch is None:
                    continue
                if now - last_touch < timedelta(hours=18):
                    continue
                mood = self._resolve_daily_mood(now.date())
                message = self._proactive_message_for_user(profile.user_id, mood, kind="follow_up")
                self._send_telegram_notification(profile.chat_id, message)
        finally:
            self._release_job_lock(lock)

    def _has_recent_proactive_send(self, user_id: str, within_hours: int = 24) -> bool:
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
                    SELECT 1
                    FROM proactive_message_audit
                    WHERE user_id = %s
                      AND success = TRUE
                      AND sent_at >= NOW() - (%s::text || ' hours')::interval
                    LIMIT 1
                    """,
                    (str(user_id), max(1, int(within_hours))),
                )
                return cursor.fetchone() is not None
        except Exception:  # noqa: BLE001
            return False
        finally:
            if connection is not None:
                connection.close()

    def _execute_task(self, task: dict[str, Any]) -> tuple[bool, str, str]:
        task_type = str(task.get("type", "custom")).strip().lower()
        if task_type == "reminder":
            return self._execute_reminder_task(task)
        if task_type == "workflow":
            return self._execute_workflow_task(task)
        if task_type == "self_optimization":
            return self._execute_self_optimization_task(task)
        if task_type == "memory_reflection":
            return True, "memory_reflection_completed", ""
        if task_type == "proactive_daily_dispatcher":
            return self._execute_proactive_dispatcher(task)
        if task_type == "proactive_message":
            return self._execute_proactive_message_task(task)
        return True, "custom_task_processed", ""

    def _execute_reminder_task(self, task: dict[str, Any]) -> tuple[bool, str, str]:
        status = str(task.get("status", "PENDING")).upper()
        if status in _TERMINAL_REMINDER_STATES and bool(task.get("one_time", False)):
            return True, "already_terminal", ""

        chat_id = self._resolve_reminder_chat_id(task)
        if chat_id is None:
            task["status"] = "FAILED"
            task["last_error"] = "chat_id missing or invalid"
            return False, "", "chat_id missing or invalid"

        user_timezone = str(task.get("user_timezone", task.get("timezone", "UTC"))).strip() or "UTC"
        now_utc = datetime.now(timezone.utc)
        message = self._render_reminder_text_with_local_time(str(task.get("message", "Reminder")), now_utc, user_timezone)
        sent, reason = self._send_telegram_notification(chat_id, message)
        if sent:
            task["status"] = "SENT"
            task["last_error"] = ""
            task["retry_count"] = 0
            if not bool(task.get("one_time", False)):
                task["status"] = "PENDING"
            return True, f"reminder_sent_chat_{chat_id}", ""

        retry_count = max(0, int(task.get("retry_count", 0))) + 1
        task["retry_count"] = retry_count
        task["last_error"] = reason or "transient_error"
        max_retries = max(1, int(task.get("max_retries", 3) or 3))
        if reason in {"chat_not_found", "forbidden", "chat_missing"} or retry_count >= max_retries:
            task["status"] = "FAILED"
            return False, "", f"reminder_failed:{reason}"
        task["status"] = "RETRY"
        return False, "", f"reminder_retry:{reason}"

    def _execute_workflow_task(self, task: dict[str, Any]) -> tuple[bool, str, str]:
        steps = task.get("steps", [])
        if not isinstance(steps, list) or not steps:
            return True, "workflow_skipped_no_steps", ""
        outputs: list[str] = []
        context: dict[str, Any] = {
            "task_name": str(task.get("name", "unknown")),
            "task": task,
            "state": task.setdefault("_state", {}),
            "now_utc": datetime.now(timezone.utc).isoformat(),
        }
        for step in steps:
            if not isinstance(step, dict):
                continue
            action = str(step.get("action", "")).strip().lower()
            if action == "log":
                outputs.append(str(step.get("message", "")))
            elif action == "notify":
                notify_user_id = self._resolve_notify_user_id(task)
                if notify_user_id is None:
                    continue
                sent, reason = self._send_telegram_notification(notify_user_id, str(step.get("message", "Task triggered")))
                outputs.append("notify_sent" if sent else f"notify_failed:{reason}")
            elif action == "set_state":
                key = str(step.get("key", "")).strip()
                if key:
                    context["state"][key] = step.get("value")
                    outputs.append(f"set_state:{key}")
            elif action == "set":
                key = str(step.get("key", "")).strip()
                if key:
                    context[key] = step.get("value")
                    outputs.append(f"set:{key}")
        return True, "; ".join(outputs) if outputs else "workflow_completed", ""

    def _execute_self_optimization_task(self, task: dict[str, Any]) -> tuple[bool, str, str]:
        summary = self._reinforcement.summarize_recent_patterns(window=500)
        avg_score = float(summary.get("avg_score", 0.0) or 0.0)
        notes: list[str] = []
        try:
            agents_path = resolve_config_file("agents.yaml")
            personality_path = resolve_config_file("personality.yaml")
            personality = PersonalityAgent(agents_path, personality_path)
            if avg_score < -0.2:
                personality.adjust_trait("system", "warmth", 1)
                personality.adjust_trait("system", "assertiveness", -1)
                notes.append("warmth_plus_assertiveness_minus")
            elif avg_score > 0.4:
                personality.adjust_trait("system", "curiosity", 1)
                notes.append("curiosity_plus")
        except Exception as exc:  # noqa: BLE001
            notes.append(f"personality_adjustment_skipped:{exc}")
        self._decision_logger.log(
            event_type="weekly_self_optimization",
            summary="Completed weekly self-optimization cycle",
            source="scheduler",
            details={
                "avg_score": avg_score,
                "strong_areas": list(summary.get("strong_areas", [])),
                "weak_areas": list(summary.get("weak_areas", [])),
                "notes": notes,
            },
        )
        return True, f"self_optimization_avg={avg_score}", ""

    def _execute_proactive_dispatcher(self, task: dict[str, Any]) -> tuple[bool, str, str]:
        del task
        today = datetime.now(timezone.utc).date()
        created = 0
        for profile in self._active_user_profiles(limit=1000):
            if profile.proactive_opt_out:
                continue
            if not profile.chat_id:
                continue
            frequency = (profile.interaction_frequency or "normal").strip().lower()
            max_daily = 1 if frequency in {"low", "rare"} else (3 if frequency in {"high", "frequent"} else 2)
            num_messages = random.randint(1, min(3, max_daily))
            day_tz = profile.timezone or "UTC"
            if self._count_scheduled_proactive(profile.user_id, today) >= max_daily:
                continue
            for run_at in self._random_daily_times(today, day_tz, num_messages):
                message_kind = random.choice(["checkin", "follow_up", "fact", "support", "curiosity", "joke", "reflection"])
                proactive_task = {
                    "name": f"proactive_{profile.user_id}_{int(run_at.timestamp())}",
                    "type": "proactive_message",
                    "interval": "once",
                    "one_time": True,
                    "enabled": True,
                    "run_at": run_at.isoformat(),
                    "timezone": day_tz,
                    "user_timezone": day_tz,
                    "chat_id": profile.chat_id,
                    "notify_user_id": int(profile.user_id) if str(profile.user_id).isdigit() else profile.telegram_user_id,
                    "language": profile.preferred_language,
                    "message_kind": message_kind,
                    "max_retries": 1,
                    "retry_delay_seconds": 30,
                }
                self.tasks.append(proactive_task)
                self._upsert_task_job(proactive_task)
                created += 1
        return True, f"proactive_messages_scheduled={created}", ""

    def _count_scheduled_proactive(self, user_id: str, day_utc: date) -> int:
        count = 0
        for task in self.tasks:
            if str(task.get("type", "")) != "proactive_message":
                continue
            if str(task.get("notify_user_id", "")) != str(user_id):
                continue
            run_at = self._parse_iso_timestamp(task.get("run_at"))
            if run_at is None:
                continue
            if run_at.date() == day_utc:
                count += 1
        return count

    def _execute_proactive_message_task(self, task: dict[str, Any]) -> tuple[bool, str, str]:
        chat_id = self._resolve_reminder_chat_id(task)
        if chat_id is None:
            return False, "", "chat_id missing for proactive message"
        user_id = str(task.get("notify_user_id", "")).strip() or str(task.get("chat_id", ""))
        mood = self._resolve_daily_mood(datetime.now(timezone.utc).date())
        kind = str(task.get("message_kind", "checkin") or "checkin")
        message = self._proactive_message_for_user(user_id=user_id, mood=mood, kind=kind)
        sent, reason = self._send_telegram_notification(chat_id, message)
        self._record_proactive_audit(
            user_id=user_id,
            scheduled_at=self._parse_iso_timestamp(task.get("run_at")) or datetime.now(timezone.utc),
            sent_at=datetime.now(timezone.utc) if sent else None,
            kind=kind,
            mood=mood,
            success=sent,
            details={"reason": reason or "", "chat_id": chat_id},
        )
        if sent:
            return True, "proactive_sent", ""
        return False, "", f"proactive_send_failed:{reason}"

    def _record_proactive_audit(
        self,
        *,
        user_id: str,
        scheduled_at: datetime,
        sent_at: datetime | None,
        kind: str,
        mood: str,
        success: bool,
        details: dict[str, Any],
    ) -> None:
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
                    INSERT INTO proactive_message_audit (
                        user_id, scheduled_at, sent_at, message_kind, mood, success, details
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        user_id,
                        scheduled_at,
                        sent_at,
                        kind,
                        mood,
                        bool(success),
                        json.dumps(details),
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("proactive_audit_write_failed: %s", exc)
        finally:
            if connection is not None:
                connection.close()

    def _active_user_profiles(self, limit: int = 200) -> list[Any]:
        connection = None
        profiles: list[Any] = []
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
                    SELECT user_id
                    FROM users
                    ORDER BY COALESCE(last_interaction, created_at) DESC
                    LIMIT %s
                    """,
                    (max(1, int(limit)),),
                )
                rows = cursor.fetchall() or []
            for row in rows:
                user_id = str(row[0])
                profiles.append(self._user_profiles.get_personalization_profile(user_id))
        except Exception as exc:  # noqa: BLE001
            logger.warning("scheduler_user_profile_query_failed", extra={"event": "scheduler_user_profile_query_failed", "error": str(exc)})
        finally:
            if connection is not None:
                connection.close()
        return profiles

    @staticmethod
    def _resolve_daily_mood(target_day: date) -> str:
        moods = ["curious", "playful", "reflective", "supportive"]
        return moods[target_day.toordinal() % len(moods)]

    @staticmethod
    def _random_daily_times(day_utc: date, timezone_name: str, count: int) -> list[datetime]:
        try:
            tz = ZoneInfo(timezone_name)
        except Exception:  # noqa: BLE001
            tz = ZoneInfo("UTC")
        times: list[datetime] = []
        for _ in range(max(1, int(count))):
            hour = random.randint(9, 20)
            minute = random.randint(0, 59)
            local_dt = datetime(day_utc.year, day_utc.month, day_utc.day, hour, minute, tzinfo=tz)
            times.append(local_dt.astimezone(UTC))
        return sorted(times)

    def _proactive_message_for_user(self, user_id: str, mood: str, kind: str) -> str:
        profile = self._user_profiles.get_personalization_profile(user_id)
        name = profile.nickname or profile.name or "there"
        language = (profile.preferred_language or "en").strip().lower()
        memory_hint = self._memory_hint_for_user(user_id)

        english_templates = {
            "checkin": f"Hi {name}, quick check-in: how is your day going so far?",
            "follow_up": f"Hi {name}, yesterday you mentioned {memory_hint}. How is it going now?",
            "fact": f"Hi {name}, curious fact for today: short breaks often improve focus and memory.",
            "support": f"Hi {name}, if today feels heavy, take one small step and I will help with the next one.",
            "curiosity": f"Hi {name}, what is one question you want to explore today?",
            "joke": f"Hi {name}, tiny joke break: why do programmers confuse Halloween and Christmas? Because OCT 31 == DEC 25.",
            "reflection": f"Hi {name}, reflective moment: what worked well for you today, and what will you improve tomorrow?",
        }
        persian_templates = {
            "checkin": f"{name} عزیز، یک احوال‌پرسی کوتاه: امروزت تا اینجا چطور بوده؟",
            "follow_up": f"{name} عزیز، دیروز گفتی {memory_hint}. الان اوضاعش چطوره؟",
            "fact": f"{name} عزیز، یک نکته جالب امروز: استراحت‌های کوتاه معمولاً تمرکز و حافظه را بهتر می‌کنند.",
            "support": f"{name} عزیز، اگر امروز سنگین است، یک قدم خیلی کوچک بردار؛ من برای قدم بعدی کمکت می‌کنم.",
            "curiosity": f"{name} عزیز، امروز دوست داری چه سوالی را عمیق‌تر بررسی کنیم؟",
            "joke": f"{name} عزیز، یک شوخی کوتاه: چرا برنامه‌نویس‌ها هالووین و کریسمس را قاطی می‌کنند؟ چون OCT 31 == DEC 25.",
            "reflection": f"{name} عزیز، یک لحظه برای بازتاب: امروز چه چیزی خوب پیش رفت و فردا چه چیزی را بهتر می‌کنی؟",
        }
        mapping = persian_templates if language == "fa" else english_templates
        base = mapping.get(kind, mapping["checkin"])
        if mood == "playful" and language == "en":
            return base + " Mood today: playful."
        if mood == "reflective" and language == "fa":
            return base + " حال‌وهوای امروز: تأملی."
        return base

    def _memory_hint_for_user(self, user_id: str) -> str:
        client = self._redis_client()
        if client is None:
            return "something important"
        try:
            rows = client.lrange(f"her:context:{user_id}", -8, -1)
            for raw in reversed(rows):
                payload = json.loads(raw)
                if str(payload.get("role", "")).lower() == "user":
                    text = str(payload.get("message", "")).strip()
                    if text:
                        return text[:80]
        except Exception:  # noqa: BLE001
            pass
        return "something important"

    def _last_user_context_timestamp(self, user_id: str) -> datetime | None:
        del user_id
        return datetime.now(timezone.utc) - timedelta(hours=24)

    def _send_telegram_notification(self, chat_id: int, text: str) -> tuple[bool, str | None]:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            return False, "missing_token"
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = urlencode({"chat_id": str(chat_id), "text": text}).encode("utf-8")
            request = Request(url=url, data=payload, method="POST")
            with urlopen(request, timeout=15) as response:
                _ = response.read()
            return True, None
        except HTTPError as exc:
            message = str(exc).lower()
            if "404" in message:
                return False, "chat_not_found"
            if "403" in message:
                return False, "forbidden"
            return False, "transient_error"
        except Exception:  # noqa: BLE001
            return False, "transient_error"

    @staticmethod
    def _resolve_notify_user_id(task: dict[str, Any]) -> int | None:
        candidate = task.get("notify_user_id")
        if candidate is None:
            candidate = os.getenv("ADMIN_USER_ID", "")
        text = str(candidate).strip()
        if text.isdigit():
            value = int(text)
            if value > 0:
                return value
        return None

    @staticmethod
    def _coerce_chat_id(value: Any) -> int | None:
        text = str(value or "").strip()
        if text and text.lstrip("-").isdigit():
            return int(text)
        return None

    def _resolve_reminder_chat_id(self, task: dict[str, Any]) -> int | None:
        chat_id = self._coerce_chat_id(task.get("chat_id"))
        if chat_id is not None:
            return chat_id
        notify_user = self._resolve_notify_user_id(task)
        if notify_user is not None:
            return notify_user
        return None

    @staticmethod
    def _render_reminder_text_with_local_time(text: str, triggered_at_utc: datetime, timezone_name: str) -> str:
        tz_name = timezone_name.strip() or "UTC"
        try:
            local_dt = triggered_at_utc.astimezone(ZoneInfo(tz_name))
            stamp = local_dt.strftime("%Y-%m-%d %H:%M")
            return f"{text}\n\n🕒 {stamp} ({tz_name})"
        except Exception:  # noqa: BLE001
            return text

    def _normalize_task(self, task: Any) -> dict[str, Any] | None:
        if not isinstance(task, dict):
            return None
        name = str(task.get("name", "")).strip()
        if not name:
            return None
        interval = str(task.get("interval", "")).strip().lower()
        if not self.is_valid_interval(interval):
            return None
        normalized = dict(task)
        normalized["name"] = name
        normalized["interval"] = interval
        normalized["enabled"] = bool(task.get("enabled", True))
        normalized["type"] = str(task.get("type", "custom")).strip().lower() or "custom"
        normalized["one_time"] = bool(task.get("one_time", interval == "once"))
        normalized.setdefault("max_retries", 2)
        normalized.setdefault("retry_delay_seconds", 30)

        run_at = str(task.get("run_at", "")).strip()
        if run_at:
            parsed = self._parse_iso_timestamp(run_at)
            if parsed is not None:
                normalized["run_at"] = parsed.isoformat()

        at_value = str(task.get("at", "")).strip()
        if at_value and self._parse_clock(at_value) is not None:
            normalized["at"] = at_value

        timezone_name = str(task.get("timezone", self._system_timezone())).strip() or self._system_timezone()
        try:
            ZoneInfo(timezone_name)
            normalized["timezone"] = timezone_name
        except Exception:  # noqa: BLE001
            normalized["timezone"] = "UTC"

        weekdays = normalize_weekdays_input(task.get("weekdays"))
        if weekdays:
            normalized["weekdays"] = weekdays

        if normalized["type"] == "reminder":
            normalized["chat_id"] = self._coerce_chat_id(task.get("chat_id"))
            normalized["status"] = str(task.get("status", "PENDING")).upper() or "PENDING"
            normalized["retry_count"] = max(0, int(task.get("retry_count", 0) or 0))
            normalized["max_retries"] = max(1, int(task.get("max_retries", 3) or 3))
            normalized["last_error"] = str(task.get("last_error", "") or "")
            normalized["message"] = str(task.get("message", "Reminder") or "Reminder")

        return normalized

    def _serializable_tasks(self) -> list[dict[str, Any]]:
        return [{k: v for k, v in task.items() if not str(k).startswith("_")} for task in self.tasks]

    def persist_tasks(self) -> tuple[bool, str]:
        path = self._config_path or resolve_config_file("scheduler.yaml")
        try:
            payload = {"tasks": self._serializable_tasks()}
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as handle:
                yaml.safe_dump(payload, handle, sort_keys=False)
            self._publish_scheduler_state()
            return True, f"saved to {path}"
        except Exception as exc:  # noqa: BLE001
            return False, f"failed to write {path}: {exc}"

    async def run_task_now(self, name: str) -> tuple[bool, str]:
        task = self._find_task(name)
        if task is None:
            return False, "task not found"
        self._run_task_job(name)
        return True, "executed"

    def add_task(self, name: str, interval: str, task_type: str = "custom", enabled: bool = True, **kwargs: Any) -> None:
        interval = str(interval).strip().lower()
        if not self.is_valid_interval(interval):
            raise ValueError("Invalid interval. Use once|hourly|daily|weekly|every_<N>_minutes|every_<N>_hours|every_<N>_days")
        payload = {
            "name": name,
            "interval": interval,
            "type": task_type,
            "enabled": enabled,
            **kwargs,
        }
        normalized = self._normalize_task(payload)
        if normalized is None:
            raise ValueError("Task configuration is invalid")
        if str(normalized.get("type", "")).lower() == "reminder" and self._resolve_reminder_chat_id(normalized) is None:
            raise ValueError("Chat ID required for reminder tasks")
        self.tasks.append(normalized)
        self._upsert_task_job(normalized)
        self._publish_scheduler_state()

    def set_task_interval(self, name: str, interval: str) -> bool:
        interval = str(interval).strip().lower()
        if not self.is_valid_interval(interval):
            raise ValueError("Invalid interval. Use once|hourly|daily|weekly|every_<N>_minutes|every_<N>_hours|every_<N>_days")
        for task in self.tasks:
            if str(task.get("name", "")) == name:
                task["interval"] = interval
                self._upsert_task_job(task)
                self._publish_scheduler_state()
                return True
        return False

    def set_task_enabled(self, name: str, enabled: bool) -> bool:
        for task in self.tasks:
            if str(task.get("name", "")) == name:
                task["enabled"] = bool(enabled)
                self._upsert_task_job(task)
                self._publish_scheduler_state()
                return True
        return False

    def get_tasks(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self.tasks]

    def _next_run_for_task(self, task_name: str) -> str:
        if self._scheduler is None:
            return ""
        job = self._scheduler.get_job(f"task:{task_name}")
        if not job or not job.next_run_time:
            return ""
        return job.next_run_time.astimezone(timezone.utc).isoformat()

    def get_upcoming_jobs(self, limit: int = 20) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if self._scheduler is None:
            return rows
        for task in self.tasks:
            if not bool(task.get("enabled", True)):
                continue
            name = str(task.get("name", ""))
            rows.append(
                {
                    "name": name,
                    "type": task.get("type", "custom"),
                    "interval": task.get("interval", ""),
                    "timezone": task.get("timezone", self._system_timezone()),
                    "at": task.get("at", ""),
                    "run_at": task.get("run_at", ""),
                    "one_time": bool(task.get("one_time", False)),
                    "max_retries": int(task.get("max_retries", 2) or 0),
                    "retry_delay_seconds": int(task.get("retry_delay_seconds", 30) or 0),
                    "status": str(task.get("status", "PENDING")),
                    "retry_count": int(task.get("retry_count", 0) or 0),
                    "last_error": str(task.get("last_error", "") or ""),
                    "chat_id": task.get("chat_id"),
                    "next_run": self._next_run_for_task(name),
                    "enabled": bool(task.get("enabled", True)),
                }
            )
        rows.sort(key=lambda item: str(item.get("next_run", "") or "~"))
        return rows[: max(1, int(limit))]

    def _publish_scheduler_state(self) -> None:
        client = self._redis_client()
        if client is None:
            return
        try:
            payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "task_count": len(self.tasks),
                "system_tz": self._system_timezone(),
                "default_user_tz": os.getenv("USER_TIMEZONE", "UTC"),
                "upcoming": self.get_upcoming_jobs(limit=100),
            }
            client.set("her:scheduler:state", json.dumps(payload))
        except Exception:  # noqa: BLE001
            return

    def _log_job_execution(
        self,
        name: str,
        job_type: str,
        success: bool,
        result: str,
        error: str,
        execution_time: float,
        next_run: str,
    ) -> None:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "name": name,
            "type": job_type,
            "success": success,
            "result": result,
            "error": error,
            "execution_time": execution_time,
            "next_run": next_run,
        }
        self._decision_logger.log(
            event_type="scheduler_execution",
            summary=f"Task '{name}' executed ({'success' if success else 'failed'})",
            source="scheduler",
            details=payload,
        )
        client = self._redis_client()
        if client is None:
            return
        try:
            client.lpush("her:scheduler:jobs", json.dumps(payload))
            client.ltrim("her:scheduler:jobs", 0, 99)
        except Exception:  # noqa: BLE001
            return

    def _redis_client(self) -> Any:
        try:
            import redis

            return redis.Redis(
                host=os.getenv("REDIS_HOST", "redis"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                password=os.getenv("REDIS_PASSWORD", ""),
                decode_responses=True,
            )
        except Exception:  # noqa: BLE001
            return None


_scheduler: TaskScheduler | None = None


def get_scheduler() -> TaskScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = TaskScheduler()
    return _scheduler

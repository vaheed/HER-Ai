"""Task scheduler for HER AI Assistant.

Supports cron-like scheduling for:
- Hourly tasks
- Daily tasks
- Custom interval tasks
- Time-of-day reminders and workflow notifications
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import yaml

from agents.personality_agent import PersonalityAgent
from utils.config_paths import resolve_config_file
from utils.decision_log import DecisionLogger
from utils.reinforcement import ReinforcementEngine

logger = logging.getLogger(__name__)


class TaskScheduler:
    """Cron-like task scheduler for HER."""

    def __init__(self):
        self.tasks: list[dict[str, Any]] = []
        self.running = False
        self._scheduler_task: asyncio.Task | None = None
        self._config_path: Path | None = None
        self._decision_logger = DecisionLogger()
        self._reinforcement = ReinforcementEngine()

    async def start(self):
        """Start the scheduler."""
        if self.running:
            logger.warning("Scheduler already running")
            return

        self.running = True
        self._load_tasks()
        self._restore_runtime_state()
        self._recompute_all_next_runs(datetime.now(timezone.utc))
        self._publish_scheduler_state()
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("✅ Task scheduler started with %s tasks", len(self.tasks))

    async def stop(self):
        """Stop the scheduler."""
        self.running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        self._persist_runtime_state()
        self._publish_scheduler_state()
        logger.info("Task scheduler stopped")

    def _load_tasks(self):
        """Load tasks from configuration."""
        try:
            config_path = resolve_config_file("scheduler.yaml")
            self._config_path = config_path
            if not config_path.exists():
                logger.debug("No scheduler.yaml found, using defaults")
                self.tasks = []
                return

            with config_path.open("r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}

            raw_tasks = config.get("tasks", [])
            valid_tasks: list[dict[str, Any]] = []
            for raw_task in raw_tasks:
                normalized = self._normalize_task(raw_task)
                if normalized is None:
                    continue
                valid_tasks.append(normalized)
            if not valid_tasks:
                valid_tasks = self._load_tasks_override_from_redis()
            self.tasks = valid_tasks
            self._ensure_baseline_tasks()
            logger.info("Loaded %s scheduled tasks", len(self.tasks))

        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to load scheduler config: %s", exc)
            self.tasks = self._load_tasks_override_from_redis()
            self._ensure_baseline_tasks()

    def _ensure_baseline_tasks(self) -> None:
        reflection_required = {
            "name": "memory_reflection",
            "type": "memory_reflection",
            "interval": "hourly",
            "enabled": True,
            "max_retries": 2,
            "retry_delay_seconds": 30,
        }
        self_opt_required = {
            "name": "weekly_self_optimization",
            "type": "self_optimization",
            "interval": "weekly",
            "enabled": True,
            "at": "18:00",
            "timezone": os.getenv("TZ", "UTC"),
            "max_retries": 1,
            "retry_delay_seconds": 60,
        }
        for task in self.tasks:
            if str(task.get("name", "")).strip() == "memory_reflection":
                task["enabled"] = True
                if str(task.get("interval", "")).strip().lower() != "hourly":
                    task["interval"] = "hourly"
                task.setdefault("max_retries", 2)
                task.setdefault("retry_delay_seconds", 30)
                break
        else:
            self.tasks.append(reflection_required)

        for task in self.tasks:
            if str(task.get("name", "")).strip() == "weekly_self_optimization":
                task["enabled"] = True
                if str(task.get("interval", "")).strip().lower() != "weekly":
                    task["interval"] = "weekly"
                task.setdefault("at", "18:00")
                task.setdefault("timezone", os.getenv("TZ", "UTC"))
                task.setdefault("max_retries", 1)
                task.setdefault("retry_delay_seconds", 60)
                break
        else:
            self.tasks.append(self_opt_required)

    def _normalize_task(self, task: Any) -> dict[str, Any] | None:
        if not isinstance(task, dict):
            logger.warning("Skipping invalid scheduler task entry: expected object")
            return None

        name = str(task.get("name", "")).strip()
        interval = str(task.get("interval", "")).strip().lower()
        task_type = str(task.get("type", "custom")).strip().lower() or "custom"

        if not name:
            logger.warning("Skipping scheduler task with missing name")
            return None
        if not self.is_valid_interval(interval):
            logger.warning("Skipping scheduler task '%s': invalid interval '%s'", name, interval)
            return None

        normalized = dict(task)
        normalized["name"] = name
        normalized["interval"] = interval
        normalized["type"] = task_type
        normalized["enabled"] = bool(task.get("enabled", True))
        normalized["one_time"] = bool(task.get("one_time", interval == "once"))
        normalized.setdefault("max_retries", 2)
        normalized.setdefault("retry_delay_seconds", 30)

        run_at_value = str(task.get("run_at", "")).strip()
        if run_at_value:
            parsed_run_at = self._parse_iso_timestamp(run_at_value)
            if parsed_run_at is None:
                logger.warning("Task '%s' has invalid run_at '%s' (expected ISO8601)", name, run_at_value)
                normalized.pop("run_at", None)
            else:
                normalized["run_at"] = parsed_run_at.isoformat()

        at_value = str(task.get("at", "")).strip()
        if at_value and not self._is_valid_clock_time(at_value):
            logger.warning("Task '%s' has invalid 'at' format '%s' (expected HH:MM)", name, at_value)
            normalized.pop("at", None)

        tz_name = str(task.get("timezone", os.getenv("TZ", "UTC"))).strip() or "UTC"
        try:
            ZoneInfo(tz_name)
            normalized["timezone"] = tz_name
        except Exception:  # noqa: BLE001
            logger.warning("Task '%s' timezone '%s' invalid, using UTC", name, tz_name)
            normalized["timezone"] = "UTC"

        weekdays = task.get("weekdays")
        if weekdays is not None:
            normalized_weekdays = self._normalize_weekdays(weekdays)
            if normalized_weekdays:
                normalized["weekdays"] = normalized_weekdays
            else:
                normalized.pop("weekdays", None)

        return normalized

    @staticmethod
    def is_valid_interval(interval: str) -> bool:
        """Validate supported interval formats."""
        if interval in {"hourly", "daily", "weekly", "once"}:
            return True
        if interval.startswith("every_"):
            parts = interval.split("_")
            if len(parts) != 3 or not parts[1].isdigit():
                return False
            return parts[2] in {"minutes", "hours", "days"}
        return False

    @staticmethod
    def _is_valid_clock_time(value: str) -> bool:
        parts = value.split(":")
        if len(parts) != 2:
            return False
        if not parts[0].isdigit() or not parts[1].isdigit():
            return False
        hour, minute = int(parts[0]), int(parts[1])
        return 0 <= hour <= 23 and 0 <= minute <= 59

    @staticmethod
    def _normalize_weekdays(weekdays: Any) -> list[int]:
        if not isinstance(weekdays, list):
            return []

        mapping = {
            "mon": 0,
            "monday": 0,
            "tue": 1,
            "tuesday": 1,
            "wed": 2,
            "wednesday": 2,
            "thu": 3,
            "thursday": 3,
            "fri": 4,
            "friday": 4,
            "sat": 5,
            "saturday": 5,
            "sun": 6,
            "sunday": 6,
        }

        normalized: set[int] = set()
        for item in weekdays:
            if isinstance(item, int) and 0 <= item <= 6:
                normalized.add(item)
                continue
            text = str(item).strip().lower()
            if text in mapping:
                normalized.add(mapping[text])

        return sorted(normalized)

    def _serializable_tasks(self) -> list[dict[str, Any]]:
        """Return task list safe for config persistence."""
        serializable: list[dict[str, Any]] = []
        for task in self.tasks:
            serializable.append({k: v for k, v in task.items() if not str(k).startswith("_")})
        return serializable

    def persist_tasks(self) -> tuple[bool, str]:
        """Persist scheduler tasks back to scheduler.yaml."""
        path = self._config_path or resolve_config_file("scheduler.yaml")
        try:
            payload = {"tasks": self._serializable_tasks()}
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as handle:
                yaml.safe_dump(payload, handle, sort_keys=False)
            self._config_path = path
            self._publish_scheduler_state()
            return True, f"saved to {path}"
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to persist scheduler tasks to %s: %s", path, exc)
            ok, detail = self._persist_tasks_override_to_redis()
            if ok:
                logger.warning(
                    "Scheduler config write failed at %s; persisted task set to Redis fallback. reason=%s",
                    path,
                    exc,
                )
                return True, f"saved to Redis fallback ({detail}); config write failed: {exc}"
            if "Permission denied" in str(exc):
                logger.warning(
                    "Scheduler config path is not writable (%s). "
                    "Set HER_CONFIG_DIR to writable path or use writable /app/config mount.",
                    path,
                )
            return False, f"failed to write {path} and Redis fallback: {exc}"

    def _load_tasks_override_from_redis(self) -> list[dict[str, Any]]:
        client = self._redis_client()
        if client is None:
            return []
        try:
            raw = client.get("her:scheduler:tasks_override")
            if not raw:
                return []
            payload = json.loads(raw)
            raw_tasks = payload.get("tasks", []) if isinstance(payload, dict) else []
            loaded: list[dict[str, Any]] = []
            for raw_task in raw_tasks:
                normalized = self._normalize_task(raw_task)
                if normalized is not None:
                    loaded.append(normalized)
            if loaded:
                logger.info("Loaded %s scheduler tasks from Redis override", len(loaded))
            return loaded
        except Exception:  # noqa: BLE001
            return []

    def _persist_tasks_override_to_redis(self) -> tuple[bool, str]:
        client = self._redis_client()
        if client is None:
            return False, "redis unavailable"
        try:
            payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "tasks": self._serializable_tasks(),
            }
            client.set("her:scheduler:tasks_override", json.dumps(payload))
            return True, "her:scheduler:tasks_override"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    async def _scheduler_loop(self):
        """Main scheduler loop."""
        while self.running:
            try:
                now = datetime.now(timezone.utc)
                dirty = False
                for task in self.tasks:
                    if not task.get("enabled", True):
                        continue

                    if self._should_run(now, task):
                        success = await self._execute_task(task)
                        if success or not bool(task.get("retry_on_failure", True)):
                            task["_last_run"] = now.isoformat()
                        dirty = True

                    next_run = self._compute_next_run(now, task)
                    if next_run:
                        serialized = next_run.isoformat()
                        if task.get("_next_run") != serialized:
                            task["_next_run"] = serialized
                            dirty = True
                    elif task.get("_next_run"):
                        task.pop("_next_run", None)
                        dirty = True

                if dirty:
                    self._persist_runtime_state()
                    self._publish_scheduler_state()

                # Check every minute
                await asyncio.sleep(60)

            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                logger.exception("Error in scheduler loop: %s", exc)
                await asyncio.sleep(60)

    @staticmethod
    def _parse_iso_timestamp(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(str(value))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_interval_delta(interval: str) -> timedelta | None:
        if interval == "hourly":
            return timedelta(hours=1)
        if interval == "daily":
            return timedelta(days=1)
        if interval == "weekly":
            return timedelta(weeks=1)
        if interval.startswith("every_"):
            parts = interval.split("_")
            if len(parts) == 3 and parts[1].isdigit():
                value = int(parts[1])
                unit = parts[2]
                if unit == "minutes":
                    return timedelta(minutes=value)
                if unit == "hours":
                    return timedelta(hours=value)
                if unit == "days":
                    return timedelta(days=value)
        return None

    @staticmethod
    def _parse_clock_time(value: str) -> tuple[int, int] | None:
        if not TaskScheduler._is_valid_clock_time(value):
            return None
        hour_s, minute_s = value.split(":", 1)
        return int(hour_s), int(minute_s)

    def _compute_next_time_based_run(
        self,
        now_utc: datetime,
        task: dict[str, Any],
        interval: str,
        last_run_dt: datetime | None,
    ) -> datetime | None:
        at_value = str(task.get("at", "")).strip()
        parsed_clock = self._parse_clock_time(at_value)
        if parsed_clock is None:
            return None

        tz_name = str(task.get("timezone", os.getenv("TZ", "UTC"))).strip() or "UTC"
        tz = ZoneInfo(tz_name)
        local_now = now_utc.astimezone(tz)
        hour, minute = parsed_clock
        candidate_local = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        weekdays = self._normalize_weekdays(task.get("weekdays", []))

        if interval == "daily":
            if candidate_local <= local_now:
                candidate_local += timedelta(days=1)
            if weekdays:
                while candidate_local.weekday() not in weekdays:
                    candidate_local += timedelta(days=1)
            return candidate_local.astimezone(timezone.utc)

        if interval == "weekly":
            if weekdays:
                if candidate_local <= local_now:
                    candidate_local += timedelta(days=1)
                while candidate_local.weekday() not in weekdays:
                    candidate_local += timedelta(days=1)
                return candidate_local.astimezone(timezone.utc)

            anchor_weekday = local_now.weekday()
            if last_run_dt is not None:
                anchor_weekday = last_run_dt.astimezone(tz).weekday()

            # Align candidate with chosen weekday, then ensure it's in the future.
            day_shift = (anchor_weekday - candidate_local.weekday()) % 7
            candidate_local += timedelta(days=day_shift)
            if candidate_local <= local_now:
                candidate_local += timedelta(days=7)
            return candidate_local.astimezone(timezone.utc)

        return None

    def _compute_next_run(self, now_utc: datetime, task: dict[str, Any]) -> datetime | None:
        interval = str(task.get("interval", ""))
        last_run_dt = self._parse_iso_timestamp(task.get("_last_run"))
        run_at_dt = self._parse_iso_timestamp(task.get("run_at"))

        if run_at_dt is not None:
            if last_run_dt is not None and last_run_dt >= run_at_dt:
                return None
            return run_at_dt

        if interval == "once":
            return None

        time_based_next = self._compute_next_time_based_run(now_utc, task, interval, last_run_dt)
        if time_based_next is not None:
            return time_based_next

        delta = self._parse_interval_delta(interval)
        if delta is None:
            return None

        if last_run_dt is None:
            return now_utc
        return last_run_dt + delta

    def _should_run(self, now_utc: datetime, task: dict[str, Any]) -> bool:
        next_run_dt = self._parse_iso_timestamp(task.get("_next_run"))
        if next_run_dt is None:
            next_run_dt = self._compute_next_run(now_utc, task)
            if next_run_dt is not None:
                task["_next_run"] = next_run_dt.isoformat()

        if next_run_dt is None:
            return False

        return now_utc >= next_run_dt

    async def _execute_task(self, task: dict[str, Any]) -> bool:
        """Execute a scheduled task."""
        task_name = task.get("name", "unknown")
        task_type = task.get("type", "custom")
        max_retries = max(0, int(task.get("max_retries", 2) or 0))
        retry_delay = max(1, int(task.get("retry_delay_seconds", 30) or 30))
        attempts_total = max_retries + 1
        attempt = 0
        success = False
        result = ""
        error = ""
        execution_time = 0.0

        while attempt < attempts_total and not success:
            attempt += 1
            start_time = time.time()
            logger.info(
                "Executing scheduled task: %s (type: %s, attempt %s/%s)",
                task_name,
                task_type,
                attempt,
                attempts_total,
            )
            result = ""
            error = ""
            try:
                if task_type == "twitter":
                    result = await self._execute_twitter_task(task)
                    success = True
                elif task_type == "memory_reflection":
                    await self._execute_reflection_task(task)
                    success = True
                    result = "Memory reflection completed"
                elif task_type == "custom":
                    await self._execute_custom_task(task)
                    success = True
                    result = "Custom task processed"
                elif task_type == "workflow":
                    result = await self._execute_workflow_task(task)
                    success = True
                elif task_type == "reminder":
                    result = await self._execute_reminder_task(task)
                    success = result.startswith("Reminder sent")
                    if not success:
                        error = result
                elif task_type == "self_optimization":
                    result = await self._execute_self_optimization_task(task)
                    success = True
                else:
                    error = f"Unknown task type: {task_type}"
                    logger.warning(error)
            except Exception as exc:  # noqa: BLE001
                error = str(exc)
                logger.exception("Task execution failed: %s", exc)
            execution_time = time.time() - start_time
            if not success and attempt < attempts_total:
                await asyncio.sleep(retry_delay)

        next_run = task.get("_next_run", "")
        self._log_job_execution(task_name, task_type, success, result, error, execution_time, str(next_run))
        self._decision_logger.log(
            event_type="scheduler_execution",
            summary=f"Task '{task_name}' executed ({'success' if success else 'failed'})",
            source="scheduler",
            details={
                "task": task_name,
                "type": task_type,
                "success": success,
                "error": error,
                "next_run": str(next_run),
                "attempts": attempt,
            },
        )
        if success and bool(task.get("one_time", False)):
            task["enabled"] = False
            task.pop("_next_run", None)
        return success

    def _log_job_execution(
        self,
        name: str,
        job_type: str,
        success: bool,
        result: str,
        error: str,
        execution_time: float,
        next_run: str,
    ):
        """Log job execution to Redis."""
        try:
            import redis

            redis_host = os.getenv("REDIS_HOST", "redis")
            redis_port = int(os.getenv("REDIS_PORT", "6379"))
            redis_password = os.getenv("REDIS_PASSWORD", "")

            redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                password=redis_password,
                decode_responses=True,
            )

            now = datetime.now(timezone.utc)
            payload = {
                "timestamp": now.isoformat(),
                "name": name,
                "type": job_type,
                "success": success,
                "result": result,
                "error": error,
                "execution_time": execution_time,
                "next_run": next_run,
            }

            redis_client.lpush("her:scheduler:jobs", json.dumps(payload))
            redis_client.ltrim("her:scheduler:jobs", 0, 99)
        except Exception:  # noqa: BLE001
            logger.warning("Failed to log scheduled job execution to Redis")

    async def _execute_twitter_task(self, task: dict[str, Any]):
        """Execute Twitter scheduled task."""
        try:
            from her_mcp.twitter_tools import TwitterConfigTool

            twitter_config = TwitterConfigTool()
            result = twitter_config._run(action="execute")
            logger.info("Twitter task result: %s", result)
            return str(result)

        except Exception as exc:  # noqa: BLE001
            logger.error("Twitter task failed: %s", exc)
            return f"Twitter task failed: {exc}"

    async def _execute_reflection_task(self, task: dict[str, Any]):
        """Execute memory reflection task."""
        logger.info("Memory reflection task executed")

    async def _execute_custom_task(self, task: dict[str, Any]):
        """Execute custom task."""
        command = task.get("command")
        if command:
            logger.info("Executing custom command: %s", command)

    async def _execute_reminder_task(self, task: dict[str, Any]) -> str:
        user_id = self._resolve_notify_user_id(task)
        if user_id is None:
            return "Reminder failed: notify_user_id missing"

        message = str(task.get("message", "Reminder"))
        sent = await self._send_telegram_notification(user_id, message)
        if sent:
            return f"Reminder sent to {user_id}"
        return f"Reminder failed for {user_id}"

    async def _execute_self_optimization_task(self, task: dict[str, Any]) -> str:
        summary = self._reinforcement.summarize_recent_patterns(window=500)
        avg_score = float(summary.get("avg_score", 0.0) or 0.0)
        weak_areas = list(summary.get("weak_areas", []))
        strong_areas = list(summary.get("strong_areas", []))

        personality_notes: list[str] = []
        try:
            agents_path = resolve_config_file("agents.yaml")
            personality_path = resolve_config_file("personality.yaml")
            personality = PersonalityAgent(agents_path, personality_path)

            if avg_score < -0.2:
                personality.adjust_trait("system", "warmth", 1)
                personality.adjust_trait("system", "assertiveness", -1)
                personality_notes.append("Adjusted personality: warmth +1, assertiveness -1")
            elif avg_score > 0.4:
                personality.adjust_trait("system", "curiosity", 1)
                personality_notes.append("Adjusted personality: curiosity +1")
            else:
                personality_notes.append("No personality adjustment needed this cycle")
        except Exception as exc:  # noqa: BLE001
            personality_notes.append(f"Personality adjustment skipped: {exc}")

        if weak_areas:
            learning_task_name = "self_learning_focus"
            existing = {str(t.get("name", "")) for t in self.tasks}
            message = (
                "Self-learning focus for this week: "
                + ", ".join(weak_areas[:3])
                + ". Prioritize stronger clarity, empathy, and actionable guidance."
            )
            if learning_task_name in existing:
                for scheduled in self.tasks:
                    if str(scheduled.get("name", "")) == learning_task_name:
                        scheduled["message"] = message
                        scheduled["enabled"] = True
                        break
            else:
                notify_user_id = self._resolve_notify_user_id(task)
                if notify_user_id is None:
                    admin_id = str(os.getenv("ADMIN_USER_ID", "")).strip()
                    notify_user_id = int(admin_id) if admin_id.isdigit() else None
                self.add_task(
                    name=learning_task_name,
                    interval="every_2_days",
                    task_type="reminder",
                    enabled=True,
                    message=message,
                    notify_user_id=notify_user_id,
                    max_retries=1,
                    retry_delay_seconds=60,
                )
            self.persist_tasks()

        self._decision_logger.log(
            event_type="weekly_self_optimization",
            summary="Completed weekly self-optimization cycle",
            source="scheduler",
            details={
                "interaction_count": int(summary.get("count", 0) or 0),
                "avg_score": avg_score,
                "weak_areas": weak_areas,
                "strong_areas": strong_areas,
                "personality_notes": personality_notes,
            },
        )
        return (
            "Weekly self-optimization complete. "
            f"avg_score={avg_score}, weak_areas={weak_areas[:3]}, strong_areas={strong_areas[:3]}"
        )

    async def _send_telegram_notification(self, chat_id: int, text: str) -> bool:
        """Send scheduler notifications via Telegram Bot API."""
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            logger.warning("Cannot send scheduler notification: TELEGRAM_BOT_TOKEN missing")
            return False
        try:
            from telegram import Bot

            bot = Bot(token=token)
            await bot.send_message(chat_id=chat_id, text=text)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to send scheduler Telegram notification: %s", exc)
            return False

    @staticmethod
    def _resolve_notify_user_id(task: dict[str, Any]) -> int | None:
        candidate = task.get("notify_user_id")
        if candidate is None:
            candidate = os.getenv("ADMIN_USER_ID", "")
        text = str(candidate).strip()
        if text.isdigit():
            return int(text)
        return None

    @staticmethod
    def _safe_eval(expression: str, context: dict[str, Any]) -> Any:
        safe_globals = {
            "__builtins__": {},
            "abs": abs,
            "min": min,
            "max": max,
            "sum": sum,
            "len": len,
            "round": round,
            "int": int,
            "float": float,
            "str": str,
            "bool": bool,
        }
        return eval(expression, safe_globals, context)  # noqa: S307

    @staticmethod
    def _format_template(template: str, context: dict[str, Any]) -> str:
        rendered = template
        for key, value in context.items():
            placeholder = "{" + str(key) + "}"
            if placeholder in rendered:
                rendered = rendered.replace(placeholder, str(value))
        return rendered

    @staticmethod
    def _fetch_json(url: str, timeout_seconds: int = 10) -> dict[str, Any] | list[Any] | None:
        try:
            with urlopen(url, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return None

    async def _execute_workflow_step(
        self,
        task: dict[str, Any],
        step: dict[str, Any],
        context: dict[str, Any],
    ) -> str:
        if "when" in step:
            when_expr = str(step.get("when", "True"))
            try:
                if not bool(self._safe_eval(when_expr, context)):
                    return "step skipped (when=false)"
            except NameError as exc:
                logger.warning(
                    "Workflow task '%s' step skipped due to undefined name in when='%s': %s",
                    task.get("name", "unknown"),
                    when_expr,
                    exc,
                )
                return "step skipped (when=undefined name)"

        action = str(step.get("action", "")).strip().lower()
        if not action:
            return "step skipped: missing action"

        if action == "fetch_json":
            url = self._format_template(str(step.get("url", "")), context)
            if not url:
                return "fetch_json failed: missing url"
            data = self._fetch_json(url)
            if data is None:
                return f"fetch_json failed: {url}"
            save_as = str(step.get("save_as", "data")).strip() or "data"
            context[save_as] = data
            return f"fetch_json ok -> {save_as}"

        if action == "set":
            key = str(step.get("key", "")).strip()
            if not key:
                return "set failed: missing key"
            if "expr" in step:
                expr = str(step.get("expr", ""))
                try:
                    value = self._safe_eval(expr, context)
                except NameError as exc:
                    logger.warning(
                        "Workflow task '%s' set failed due to undefined name in expr='%s': %s",
                        task.get("name", "unknown"),
                        expr,
                        exc,
                    )
                    return "set failed: undefined name in expr"
            else:
                value = step.get("value")
            context[key] = value
            return f"set {key}"

        if action == "set_state":
            key = str(step.get("key", "")).strip()
            if not key:
                return "set_state failed: missing key"
            state = context.get("state")
            if not isinstance(state, dict):
                return "set_state failed: state unavailable"
            if "expr" in step:
                expr = str(step.get("expr", ""))
                try:
                    value = self._safe_eval(expr, context)
                except NameError as exc:
                    logger.warning(
                        "Workflow task '%s' set_state failed due to undefined name in expr='%s': %s",
                        task.get("name", "unknown"),
                        expr,
                        exc,
                    )
                    return "set_state failed: undefined name in expr"
            else:
                value = step.get("value")
            state[key] = value
            context[key] = value
            return f"set_state {key}"

        if action == "notify":
            user_id = self._resolve_notify_user_id(task)
            if user_id is None:
                return "notify failed: notify_user_id missing"
            message = self._format_template(str(step.get("message", "Task triggered")), context)
            sent = await self._send_telegram_notification(user_id, message)
            return "notify sent" if sent else "notify failed"

        if action == "webhook":
            webhook_url = self._format_template(str(step.get("url", "")), context)
            if not webhook_url:
                return "webhook failed: missing url"
            payload: Any
            if "payload_expr" in step:
                payload_expr = str(step.get("payload_expr", ""))
                try:
                    payload = self._safe_eval(payload_expr, context)
                except NameError as exc:
                    logger.warning(
                        "Workflow task '%s' webhook failed due to undefined name in payload_expr='%s': %s",
                        task.get("name", "unknown"),
                        payload_expr,
                        exc,
                    )
                    return "webhook failed: undefined name in payload_expr"
            else:
                payload = step.get("payload", {})
            request = Request(
                webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=10):
                pass
            return "webhook sent"

        if action == "log":
            message = self._format_template(str(step.get("message", "")), context)
            logger.info("Workflow task '%s': %s", task.get("name", "unknown"), message)
            return "log written"

        return f"unknown action: {action}"

    async def _execute_workflow_task(self, task: dict[str, Any]) -> str:
        """Generic chain-based workflow with condition + actions."""
        steps = task.get("steps", [])
        if not isinstance(steps, list) or not steps:
            return "workflow skipped: missing steps"

        state = task.setdefault("_state", {})
        if not isinstance(state, dict):
            state = {}
            task["_state"] = state

        context: dict[str, Any] = {
            "task_name": task.get("name", "unknown"),
            "now_utc": datetime.utcnow().isoformat() + "Z",
            "state": state,
            "task": task,
        }

        # Optional source fetch before evaluating condition.
        source_url = str(task.get("source_url", "")).strip()
        if source_url:
            rendered_url = self._format_template(source_url, context)
            source_data = self._fetch_json(rendered_url)
            if source_data is not None:
                context["source"] = source_data

        condition = str(task.get("condition_expr", "True")).strip() or "True"
        try:
            if not bool(self._safe_eval(condition, context)):
                return "condition=false"
        except NameError as exc:
            logger.warning(
                "Workflow task '%s' condition evaluated false due to undefined name in condition_expr='%s': %s",
                task.get("name", "unknown"),
                condition,
                exc,
            )
            return "condition=false (undefined name)"

        outputs: list[str] = []
        for raw_step in steps:
            if not isinstance(raw_step, dict):
                continue
            outcome = await self._execute_workflow_step(task, raw_step, context)
            outputs.append(outcome)
        return "; ".join(outputs) if outputs else "workflow completed"

    def _redis_client(self):
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

    def _persist_runtime_state(self) -> None:
        client = self._redis_client()
        if client is None:
            return
        try:
            state = {
                str(task.get("name", "")): {
                    "last_run": task.get("_last_run", ""),
                    "next_run": task.get("_next_run", ""),
                }
                for task in self.tasks
                if task.get("name")
            }
            client.set("her:scheduler:runtime_state", json.dumps(state))
        except Exception:  # noqa: BLE001
            return

    def _restore_runtime_state(self) -> None:
        client = self._redis_client()
        if client is None:
            return
        try:
            raw = client.get("her:scheduler:runtime_state")
            if not raw:
                return
            state = json.loads(raw)
            if not isinstance(state, dict):
                return
            for task in self.tasks:
                name = str(task.get("name", "")).strip()
                persisted = state.get(name, {}) if name else {}
                if not isinstance(persisted, dict):
                    continue
                last_run = str(persisted.get("last_run", "")).strip()
                next_run = str(persisted.get("next_run", "")).strip()
                if last_run:
                    task["_last_run"] = last_run
                if next_run:
                    task["_next_run"] = next_run
        except Exception:  # noqa: BLE001
            return

    def _recompute_all_next_runs(self, now_utc: datetime) -> None:
        for task in self.tasks:
            next_run = self._compute_next_run(now_utc, task)
            if next_run:
                task["_next_run"] = next_run.isoformat()
            else:
                task.pop("_next_run", None)

    def get_upcoming_jobs(self, limit: int = 20) -> list[dict[str, Any]]:
        upcoming: list[dict[str, Any]] = []
        for task in self.tasks:
            if not task.get("enabled", True):
                continue
            next_run = str(task.get("_next_run", "")).strip()
            upcoming.append(
                {
                    "name": task.get("name", "unknown"),
                    "type": task.get("type", "custom"),
                    "interval": task.get("interval", ""),
                    "timezone": task.get("timezone", os.getenv("TZ", "UTC")),
                    "at": task.get("at", ""),
                    "run_at": task.get("run_at", ""),
                    "one_time": bool(task.get("one_time", False)),
                    "max_retries": int(task.get("max_retries", 2) or 0),
                    "retry_delay_seconds": int(task.get("retry_delay_seconds", 30) or 0),
                    "next_run": next_run,
                    "enabled": bool(task.get("enabled", True)),
                }
            )

        upcoming.sort(key=lambda item: str(item.get("next_run", "")))
        return upcoming[: max(1, limit)]

    def _publish_scheduler_state(self) -> None:
        client = self._redis_client()
        if client is None:
            return
        try:
            payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "task_count": len(self.tasks),
                "upcoming": self.get_upcoming_jobs(limit=100),
            }
            client.set("her:scheduler:state", json.dumps(payload))
        except Exception:  # noqa: BLE001
            return

    def add_task(
        self,
        name: str,
        interval: str,
        task_type: str = "custom",
        enabled: bool = True,
        **kwargs: Any,
    ):
        """Add a task to the scheduler."""
        interval = interval.lower().strip()
        if not self.is_valid_interval(interval):
            raise ValueError(
                "Invalid interval. Use once|hourly|daily|weekly|every_<N>_minutes|every_<N>_hours|every_<N>_days"
            )
        task = {
            "name": name,
            "interval": interval,
            "type": task_type,
            "enabled": enabled,
            **kwargs,
        }
        normalized = self._normalize_task(task)
        if normalized is None:
            raise ValueError("Task configuration is invalid")
        self.tasks.append(normalized)
        self._recompute_all_next_runs(datetime.now(timezone.utc))
        self._persist_runtime_state()
        self._publish_scheduler_state()
        logger.info("Added scheduled task: %s (interval: %s)", name, interval)

    def set_task_interval(self, name: str, interval: str) -> bool:
        """Update interval for an existing task."""
        interval = interval.lower().strip()
        if not self.is_valid_interval(interval):
            raise ValueError(
                "Invalid interval. Use once|hourly|daily|weekly|every_<N>_minutes|every_<N>_hours|every_<N>_days"
            )
        for task in self.tasks:
            if task.get("name") == name:
                task["interval"] = interval
                task.pop("_last_run", None)
                task.pop("_next_run", None)
                self._recompute_all_next_runs(datetime.now(timezone.utc))
                self._persist_runtime_state()
                self._publish_scheduler_state()
                return True
        return False

    def set_task_enabled(self, name: str, enabled: bool) -> bool:
        """Enable/disable an existing task."""
        for task in self.tasks:
            if task.get("name") == name:
                task["enabled"] = enabled
                if enabled:
                    task.pop("_last_run", None)
                task.pop("_next_run", None)
                self._recompute_all_next_runs(datetime.now(timezone.utc))
                self._persist_runtime_state()
                self._publish_scheduler_state()
                return True
        return False

    async def run_task_now(self, name: str) -> tuple[bool, str]:
        """Execute a configured task immediately by name."""
        for task in self.tasks:
            if task.get("name") == name:
                success = await self._execute_task(task)
                now = datetime.now(timezone.utc)
                if success or not bool(task.get("retry_on_failure", True)):
                    task["_last_run"] = now.isoformat()
                next_run = self._compute_next_run(now, task)
                if next_run:
                    task["_next_run"] = next_run.isoformat()
                else:
                    task.pop("_next_run", None)
                self._persist_runtime_state()
                self._publish_scheduler_state()
                return True, "executed" if success else "failed"
        return False, "task not found"

    def get_tasks(self) -> list[dict[str, Any]]:
        """Get all scheduled tasks."""
        return self.tasks.copy()


# Global scheduler instance
_scheduler: TaskScheduler | None = None


def get_scheduler() -> TaskScheduler:
    """Get the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = TaskScheduler()
    return _scheduler

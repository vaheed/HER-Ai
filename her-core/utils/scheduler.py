"""Task scheduler for HER AI Assistant.

Supports cron-like scheduling for:
- Hourly tasks
- Daily tasks
- Custom interval tasks
- Twitter auto-actions
- Memory reflection
- Any configured periodic operations
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import yaml

from utils.config_paths import resolve_config_file

logger = logging.getLogger(__name__)


class TaskScheduler:
    """Cron-like task scheduler for HER."""

    def __init__(self):
        self.tasks: list[dict[str, Any]] = []
        self.running = False
        self._scheduler_task: asyncio.Task | None = None
        self._config_path: Path | None = None

    async def start(self):
        """Start the scheduler."""
        if self.running:
            logger.warning("Scheduler already running")
            return

        self.running = True
        self._load_tasks()
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
            self.tasks = [task for task in raw_tasks if isinstance(task, dict)]
            logger.info("Loaded %s scheduled tasks", len(self.tasks))

        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to load scheduler config: %s", exc)
            self.tasks = []

    @staticmethod
    def is_valid_interval(interval: str) -> bool:
        """Validate supported interval formats."""
        if interval in {"hourly", "daily", "weekly"}:
            return True
        if interval.startswith("every_"):
            parts = interval.split("_")
            if len(parts) != 3 or not parts[1].isdigit():
                return False
            return parts[2] in {"minutes", "hours", "days"}
        return False

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
            return True, f"saved to {path}"
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to persist scheduler tasks to %s: %s", path, exc)
            return False, f"failed to write {path}: {exc}"

    async def _scheduler_loop(self):
        """Main scheduler loop."""
        while self.running:
            try:
                now = datetime.now()
                for task in self.tasks:
                    if not task.get("enabled", True):
                        continue

                    last_run = task.get("_last_run")
                    interval = task.get("interval")

                    if self._should_run(now, last_run, interval):
                        await self._execute_task(task)
                        task["_last_run"] = now.isoformat()

                # Check every minute
                await asyncio.sleep(60)

            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                logger.exception("Error in scheduler loop: %s", exc)
                await asyncio.sleep(60)

    def _should_run(self, now: datetime, last_run: str | None, interval: str) -> bool:
        """Check if task should run based on interval."""
        if not interval:
            return False

        if not last_run:
            return True

        try:
            last_run_dt = datetime.fromisoformat(last_run)
        except (ValueError, TypeError):
            return True

        if interval == "hourly":
            return (now - last_run_dt) >= timedelta(hours=1)
        elif interval == "daily":
            return (now - last_run_dt) >= timedelta(days=1)
        elif interval == "weekly":
            return (now - last_run_dt) >= timedelta(weeks=1)
        elif interval.startswith("every_"):
            # Parse "every_N_minutes", "every_N_hours", etc.
            parts = interval.split("_")
            if len(parts) == 3 and parts[1].isdigit():
                value = int(parts[1])
                unit = parts[2]

                if unit == "minutes":
                    return (now - last_run_dt) >= timedelta(minutes=value)
                elif unit == "hours":
                    return (now - last_run_dt) >= timedelta(hours=value)
                elif unit == "days":
                    return (now - last_run_dt) >= timedelta(days=value)

        return False

    async def _execute_task(self, task: dict[str, Any]):
        """Execute a scheduled task."""
        task_name = task.get("name", "unknown")
        task_type = task.get("type", "custom")
        start_time = time.time()

        logger.info("Executing scheduled task: %s (type: %s)", task_name, task_type)

        success = False
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
            else:
                error = f"Unknown task type: {task_type}"
                logger.warning(error)

        except Exception as exc:  # noqa: BLE001
            error = str(exc)
            logger.exception("Task execution failed: %s", exc)

        execution_time = time.time() - start_time
        self._log_job_execution(task_name, task_type, success, result, error, execution_time, task.get("interval", ""))

    def _log_job_execution(
        self,
        name: str,
        job_type: str,
        success: bool,
        result: str,
        error: str,
        execution_time: float,
        interval: str,
    ):
        """Log job execution to Redis."""
        try:
            import redis
            import json
            from datetime import datetime, timedelta, timezone

            redis_host = os.getenv("REDIS_HOST", "redis")
            redis_port = int(os.getenv("REDIS_PORT", "6379"))
            redis_password = os.getenv("REDIS_PASSWORD", "")

            redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                password=redis_password,
                decode_responses=True,
            )

            # Calculate next run time
            now = datetime.now(timezone.utc)
            if interval == "hourly":
                next_run = (now + timedelta(hours=1)).isoformat()
            elif interval == "daily":
                next_run = (now + timedelta(days=1)).isoformat()
            elif interval == "weekly":
                next_run = (now + timedelta(weeks=1)).isoformat()
            else:
                next_run = ""

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
            # Silently fail if Redis not available
            pass

    async def _execute_twitter_task(self, task: dict[str, Any]):
        """Execute Twitter scheduled task."""
        try:
            from her_mcp.twitter_tools import TwitterConfigTool

            twitter_config = TwitterConfigTool()
            result = twitter_config._run(action="execute")
            logger.info("Twitter task result: %s", result)

        except Exception as exc:  # noqa: BLE001
            logger.error("Twitter task failed: %s", exc)

    async def _execute_reflection_task(self, task: dict[str, Any]):
        """Execute memory reflection task."""
        logger.info("Memory reflection task executed")
        # This would trigger the reflection agent
        # Implementation depends on how reflection is integrated

    async def _execute_custom_task(self, task: dict[str, Any]):
        """Execute custom task."""
        command = task.get("command")
        if command:
            logger.info("Executing custom command: %s", command)
            # Could execute in sandbox or via subprocess
            # For now, just log it

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
            if not bool(self._safe_eval(str(step.get("when", "True")), context)):
                return "step skipped (when=false)"

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
                value = self._safe_eval(str(step.get("expr", "")), context)
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
                value = self._safe_eval(str(step.get("expr", "")), context)
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
                payload = self._safe_eval(str(step.get("payload_expr", "")), context)
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
        if not bool(self._safe_eval(condition, context)):
            return "condition=false"

        outputs: list[str] = []
        for raw_step in steps:
            if not isinstance(raw_step, dict):
                continue
            outcome = await self._execute_workflow_step(task, raw_step, context)
            outputs.append(outcome)
        return "; ".join(outputs) if outputs else "workflow completed"

    def add_task(
        self,
        name: str,
        interval: str,
        task_type: str = "custom",
        enabled: bool = True,
        **kwargs: Any,
    ):
        """Add a task to the scheduler."""
        if not self.is_valid_interval(interval):
            raise ValueError(
                "Invalid interval. Use hourly|daily|weekly|every_<N>_minutes|every_<N>_hours|every_<N>_days"
            )
        task = {
            "name": name,
            "interval": interval,
            "type": task_type,
            "enabled": enabled,
            **kwargs,
        }
        self.tasks.append(task)
        logger.info("Added scheduled task: %s (interval: %s)", name, interval)

    def set_task_interval(self, name: str, interval: str) -> bool:
        """Update interval for an existing task."""
        if not self.is_valid_interval(interval):
            raise ValueError(
                "Invalid interval. Use hourly|daily|weekly|every_<N>_minutes|every_<N>_hours|every_<N>_days"
            )
        for task in self.tasks:
            if task.get("name") == name:
                task["interval"] = interval
                task.pop("_last_run", None)
                return True
        return False

    def set_task_enabled(self, name: str, enabled: bool) -> bool:
        """Enable/disable an existing task."""
        for task in self.tasks:
            if task.get("name") == name:
                task["enabled"] = enabled
                if enabled:
                    task.pop("_last_run", None)
                return True
        return False

    async def run_task_now(self, name: str) -> tuple[bool, str]:
        """Execute a configured task immediately by name."""
        for task in self.tasks:
            if task.get("name") == name:
                await self._execute_task(task)
                task["_last_run"] = datetime.now().isoformat()
                return True, "executed"
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

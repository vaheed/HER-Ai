import asyncio
import logging
import os
import re
import time
import threading
from datetime import UTC, datetime, timedelta
import json
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from langchain_core.messages import HumanMessage, SystemMessage
from telegram import MessageEntity, Update
from telegram.error import NetworkError, TimedOut
from telegram.ext import ContextTypes

from agents.personality_agent import PersonalityAgent
from her_mcp.sandbox_tools import SandboxExecutor, SandboxNetworkTool, SandboxSecurityScanTool
from her_mcp.tools import CurlWebSearchTool
from her_telegram.autonomous_operator import AutonomousSandboxOperator
from her_telegram.keyboards import get_admin_menu, get_personality_adjustment
from her_telegram.rate_limiter import RateLimiter
from memory.mem0_client import HERMemory
from utils.decision_log import DecisionLogger
from utils.llm_factory import build_llm
from utils.metrics import HERMetrics
from utils.reinforcement import ReinforcementEngine
from utils.autonomy import AutonomyService
from utils.schedule_helpers import (
    extract_json_object,
    interval_unit_to_base,
    normalize_weekdays_input,
    parse_clock,
    parse_relative_delta,
)
from utils.scheduler import TaskScheduler
from utils.user_profiles import UserProfileStore

logger = logging.getLogger(__name__)
CHAT_MODE = "CHAT_MODE"
ACTION_MODE = "ACTION_MODE"
ACTION_INTENT_THRESHOLD = float(os.getenv("HER_ACTION_INTENT_THRESHOLD", "0.8"))
DEFAULT_USER_TIMEZONE = os.getenv("USER_TIMEZONE", "UTC")
_INTERNET_DENIAL_PATTERN = re.compile(r"\b(no|not|cannot|can't)\b.*\binternet\b", re.IGNORECASE)
_RETRY_IN_MIN_SEC_PATTERN = re.compile(r"try again in\s+(\d+)m([\d.]+)s", re.IGNORECASE)
_RETRY_AFTER_SECONDS_PATTERN = re.compile(r"retry after\s+(\d+)s", re.IGNORECASE)
_EVERY_INTERVAL_PATTERN = re.compile(
    r"\bevery\s+(\d+)\s*(m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)\b",
    re.IGNORECASE,
)
_IN_INTERVAL_PATTERN = re.compile(
    r"\b(?:in|after)\s+(\d+)\s*(m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)\b",
    re.IGNORECASE,
)
_HOST_PATTERN = re.compile(r"\b(?:https?://)?([a-z0-9][a-z0-9.-]+\.[a-z]{2,})\b", re.IGNORECASE)
_ACTION_WORD_PATTERN = re.compile(
    r"\b(run|execute|test|check|scan|trace|traceroute|ping|dig|mtr|nmap|curl|wget)\b",
    re.IGNORECASE,
)
_SCHEDULE_WORD_PATTERN = re.compile(
    r"\b(schedule|later|async|background|remind|notify|every|daily|weekly|tomorrow|next)\b",
    re.IGNORECASE,
)
_GREETING_PATTERN = re.compile(
    r"^\s*(hello|hi|hey|yo|good morning|good afternoon|good evening|sup|what's up)\b",
    re.IGNORECASE,
)
_PROFILE_SETUP_PATTERN = re.compile(
    r"\b(setup|set up|configure|configuration|personalize|preferences|profile|reset)\b|"
    r"(تنظیم|پیکربندی|پروفایل|شخصی(?:\s*سازی)?|ریست)",
    re.IGNORECASE,
)
_ONBOARDING_QUESTION_PATTERN = re.compile(
    r"(what is your name|what should i call you|your timezone|preferred response style|"
    r"نام شما چیست|چه صدا کنم|منطقه زمانی|سبک پاسخ)",
    re.IGNORECASE,
)
_CRITICISM_PATTERN = re.compile(
    r"(چرا چرت|اشتباه|مزخرف|nonsense|wrong|you are wrong|bad answer)",
    re.IGNORECASE,
)
_WEEKDAY_TO_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
_EXAMPLE_PROMPTS: dict[str, list[str]] = {
    "chat": [
        "Help me plan my day in 3 priorities.",
        "I feel overwhelmed. Give me a 5-minute reset plan.",
        "Rewrite this text to sound more confident: ...",
        "Summarize this message in two lines: ...",
        "Role-play a tough conversation with my manager.",
        "Give me 3 options to reply politely to this message: ...",
    ],
    "memory": [
        "Remember that I prefer concise replies.",
        "Remember my birthday is October 12.",
        "What do you remember about my work goals?",
        "Use my past preferences and suggest a better routine.",
        "I changed my preference: morning workouts instead of evening.",
        "Based on our previous chats, what patterns do you see?",
    ],
    "scheduling": [
        "Remind me in 20min to call Ali.",
        "Every day at 08:30 remind me to take vitamins.",
        "After 2h remind me to send the report.",
        "Next Monday at 9am remind me to review roadmap.",
        "Every 3 days remind me to back up my laptop.",
        "Every week remind me to review finances.",
    ],
    "automation": [
        "Check BTC price every 2min and notify me when it rises 10% from current price.",
        "Every hour check my API status page and notify me if it is down.",
        "Track ETH price every 5 minutes and alert me if it drops 5% from baseline.",
        "Monitor this JSON endpoint every 10 minutes and notify on error field.",
        "Run a daily reminder workflow at 7am with a motivational message.",
        "Every weekday at 09:00 notify me with top 3 priorities.",
    ],
    "web": [
        "Search latest AI safety news and give 3 bullet points with links.",
        "Find today's top crypto headlines with sources.",
        "What is the live BTC price in USD right now?",
        "Find the latest release notes for Docker Desktop.",
        "Search best practices for PostgreSQL backup strategy.",
        "Find a beginner guide for Rust ownership model.",
    ],
    "mcp_tools": [
        "Use web search tool and compare 2 sources on this topic: ...",
        "Check MCP status and tell me which capabilities are degraded.",
        "Fetch this PDF URL and extract 5 key insights.",
        "Use sequential thinking to break down this complex task: ...",
        "Use filesystem tool to inspect runtime config differences.",
        "Tell me what tools are currently available in runtime.",
    ],
    "sandbox": [
        "Run DNS lookup for openai.com and explain the result.",
        "Check SSL certificate expiry for github.com.",
        "Test connectivity to api.github.com and report latency.",
        "Run a simple port scan for a host and summarize open ports.",
        "Check HTTP headers for https://example.com.",
        "Do a traceroute-like analysis and summarize hops.",
    ],
    "admin": [
        "/status",
        "/mcp",
        "/memories",
        "/schedule list",
        "/schedule run memory_reflection",
        "/schedule add hydrate reminder daily at=09:00 timezone=UTC message='Drink water' notify_user_id=123456789",
    ],
    "personality": [
        "Be more concise in future replies.",
        "Challenge my assumptions more directly.",
        "Use a supportive but practical tone.",
        "Ask one follow-up question after each answer.",
        "Help me stay accountable with direct check-ins.",
        "Use simpler words when explaining technical topics.",
    ],
    "productivity": [
        "Turn this goal into a 7-day action plan: ...",
        "Create a deep-work schedule for my day.",
        "Break this project into milestones and risks.",
        "Build a meeting agenda from these notes: ...",
        "Convert this messy text into clear tasks with owners.",
        "Give me a shutdown checklist for end of workday.",
    ],
}


class MessageHandlers:
    """All Telegram message and command handlers."""

    def __init__(
        self,
        conversation_agent: Any,
        memory: HERMemory,
        personality_agent: PersonalityAgent,
        admin_user_ids: list[int],
        rate_limiter: RateLimiter,
        mcp_manager: Any | None = None,
        scheduler: TaskScheduler | None = None,
        reflection_agent: Any | None = None,
        welcome_message: str = "Hi! I'm HER, your AI companion. How can I help you today?",
        group_reply_on_mention_only: bool = True,
        group_summary_every_messages: int = 25,
        workflow_event_hub: Any | None = None,
    ):
        self.conversation_agent = conversation_agent
        self.memory = memory
        self.personality_agent = personality_agent
        self.admin_user_ids = admin_user_ids
        self.rate_limiter = rate_limiter
        self.mcp_manager = mcp_manager
        self.scheduler = scheduler
        self.reflection_agent = reflection_agent
        self.welcome_message = welcome_message
        self.group_reply_on_mention_only = group_reply_on_mention_only
        self.group_summary_every_messages = max(5, group_summary_every_messages)
        self.bot_username: str | None = None
        self._llm_provider = os.getenv("LLM_PROVIDER", "ollama").lower()
        self._llm = build_llm()
        self._fallback_provider = os.getenv("LLM_FALLBACK_PROVIDER", "ollama").lower()
        fallback_enabled = os.getenv("LLM_ENABLE_FALLBACK", "true").strip().lower() in {"1", "true", "yes", "on"}
        self._fallback_llm = (
            build_llm(self._fallback_provider)
            if fallback_enabled and self._fallback_provider != self._llm_provider
            else None
        )
        sandbox_container_name = os.getenv("SANDBOX_CONTAINER_NAME", "her-sandbox")
        self._autonomous_operator = AutonomousSandboxOperator(
            llm_invoke=self._generate_response_with_failover,
            container_name=sandbox_container_name,
            max_steps=int(os.getenv("HER_AUTONOMOUS_MAX_STEPS", "5")),
            command_timeout_seconds=int(os.getenv("HER_SANDBOX_COMMAND_TIMEOUT_SECONDS", "60")),
            cpu_time_limit_seconds=int(os.getenv("HER_SANDBOX_CPU_TIME_LIMIT_SECONDS", "20")),
            memory_limit_mb=int(os.getenv("HER_SANDBOX_MEMORY_LIMIT_MB", "512")),
        )
        self._request_interpreter = None
        self._web_search_tool = CurlWebSearchTool()
        self._decision_logger = DecisionLogger()
        self._reinforcement = ReinforcementEngine()
        self._user_profiles = UserProfileStore(default_timezone=DEFAULT_USER_TIMEZONE)
        self._autonomy = AutonomyService()
        self._workflow_event_hub = workflow_event_hub
        self._metrics: HERMetrics | None = None
        self._language_cache: dict[int, tuple[str, float]] = {}
        self._llm_stream_event_counter: dict[str, int] = {}
        try:
            self._autonomy.ensure_tables()
            self._metrics = HERMetrics(
                host=os.getenv("REDIS_HOST", "redis"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                password=os.getenv("REDIS_PASSWORD", ""),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to initialize metrics recorder: %s", exc)

    def _emit_workflow_event(
        self,
        *,
        execution_id: str | None,
        event_type: str,
        node_id: str,
        status: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        if not execution_id or not self._workflow_event_hub:
            return
        if event_type == "llm_stream_token":
            count = self._llm_stream_event_counter.get(execution_id, 0) + 1
            self._llm_stream_event_counter[execution_id] = count
            # Emit every 25th token event to keep workflow websocket responsive.
            if count % 25 != 0:
                return
        if event_type == "response_sent":
            self._llm_stream_event_counter.pop(execution_id, None)
        try:
            sanitized_details = self._sanitize_event_details(details or {})
            self._workflow_event_hub.emit(
                event_type=event_type,
                execution_id=execution_id,
                node_id=node_id,
                status=status,
                details=sanitized_details,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Workflow event emit failed: %s", exc)

    def _sanitize_event_details(self, details: dict[str, Any]) -> dict[str, Any]:
        sanitized: dict[str, Any] = {}
        for key, value in details.items():
            if key == "raw_messages" and isinstance(value, list):
                compact_rows = []
                for row in value[:4]:
                    text = str(row)
                    compact_rows.append(text[:900] + ("..." if len(text) > 900 else ""))
                sanitized[key] = compact_rows
                continue
            if key in {"tool_output", "tool_error"}:
                text = str(value)
                sanitized[key] = text[-1800:] if len(text) > 1800 else text
                continue
            if isinstance(value, str):
                sanitized[key] = value[:500] + ("..." if len(value) > 500 else "")
                continue
            sanitized[key] = value
        return sanitized

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_user_ids

    def set_bot_username(self, username: str | None) -> None:
        self.bot_username = username.lower() if username else None

    async def _reply(self, update: Update, text: str, **kwargs: Any) -> None:
        message = update.effective_message
        if not message:
            logger.warning("No effective message found for reply")
            return
        await message.reply_text(text, **kwargs)

    async def _reply_markdown(self, update: Update, text: str, **kwargs: Any) -> None:
        await self._reply(update, text, parse_mode="Markdown", **kwargs)

    @staticmethod
    def _typing_chunks(text: str, chunk_size: int = 140) -> list[str]:
        content = str(text or "").strip()
        if not content:
            return []
        if len(content) <= chunk_size:
            return [content]
        parts: list[str] = []
        cursor = 0
        while cursor < len(content):
            end = min(len(content), cursor + chunk_size)
            if end < len(content):
                boundary = content.rfind(" ", cursor, end)
                if boundary > cursor + 20:
                    end = boundary
            part = content[cursor:end].strip()
            if part:
                parts.append(part)
            cursor = end
        return parts

    async def _reply_with_typing_effect(
        self,
        update: Update,
        text: str,
        *,
        min_delay_seconds: float = 0.2,
        max_delay_seconds: float = 0.55,
        chunk_size: int = 140,
    ) -> None:
        message = update.effective_message
        chat = update.effective_chat
        if not message or not chat:
            await self._reply(update, text[:3900])
            return

        chunks = self._typing_chunks(text, chunk_size=chunk_size)
        if not chunks:
            return
        if len(chunks) == 1:
            await self._reply(update, chunks[0][:3900])
            return

        sent = await message.reply_text(chunks[0][:3900])
        assembled = chunks[0]
        for part in chunks[1:]:
            try:
                await message.get_bot().send_chat_action(chat_id=chat.id, action="typing")
            except Exception:  # noqa: BLE001
                pass
            assembled = f"{assembled} {part}".strip()
            delay = min(
                max_delay_seconds,
                max(min_delay_seconds, len(part) / 650.0),
            )
            await asyncio.sleep(delay)
            try:
                await sent.edit_text(assembled[:3900])
            except Exception:  # noqa: BLE001
                await self._reply(update, assembled[:3900])
                return

    def _safe_timezone_name(self, timezone_name: str | None) -> str:
        candidate = str(timezone_name or DEFAULT_USER_TIMEZONE).strip() or "UTC"
        try:
            ZoneInfo(candidate)
            return candidate
        except Exception:  # noqa: BLE001
            return "UTC"

    def _resolve_user_timezone(self, user_id: int) -> str:
        try:
            profile = self._user_profiles.get_profile(user_id)
            return self._safe_timezone_name(profile.timezone)
        except Exception:  # noqa: BLE001
            return self._safe_timezone_name(DEFAULT_USER_TIMEZONE)

    def _persist_user_runtime_profile(self, user_id: int, chat_id: int, username: str | None = None) -> str:
        existing_tz = self._resolve_user_timezone(user_id)
        profile = self._user_profiles.persist_telegram_identity(
            user_id=user_id,
            chat_id=chat_id,
            username=username,
            timezone_name=existing_tz,
        )
        return self._safe_timezone_name(profile.timezone)

    def _resolve_reminder_chat_id(self, user_id: int, chat_id: int | None = None) -> int | None:
        if chat_id is not None:
            return int(chat_id)
        try:
            profile = self._user_profiles.get_profile(user_id)
            if profile.chat_id is not None:
                return int(profile.chat_id)
        except Exception:  # noqa: BLE001
            return None
        return None

    def _log_timezone_conversion(self, user_id: int, user_timezone: str, local_time: str, stored_utc: str) -> None:
        payload = {
            "event": "timezone_conversion",
            "user_id": user_id,
            "user_timezone": user_timezone,
            "local_time": local_time,
            "stored_utc": stored_utc,
        }
        logger.info(payload)
        self._decision_logger.log(
            event_type="timezone_conversion",
            summary=f"Reminder time normalized for user {user_id}",
            user_id=str(user_id),
            source="telegram",
            details=payload,
        )

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if self.is_admin(user_id):
            await self._reply(update, self.welcome_message, reply_markup=get_admin_menu())
            return
        await self._reply(update, self.welcome_message)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if self.is_admin(user_id):
            await self._reply_markdown(
                update,
                (
                    "*Admin Commands*\n"
                    "- `/status`\n"
                    "- `/personality`\n"
                    "- `/memories`\n"
                    "- `/reflect`\n"
                    "- `/reset`\n"
                    "- `/mcp`\n"
                    "- `/schedule`\n"
                    "- `/example`\n"
                    "- `/help`"
                ),
                reply_markup=get_admin_menu(),
            )
            return
        await self._reply_markdown(
            update,
            (
                "*Public Commands*\n"
                "- `/start`\n"
                "- `/example`\n"
                "- `/help`"
            ),
        )

    @staticmethod
    def _chunk_lines(lines: list[str], max_chars: int = 3500) -> list[str]:
        chunks: list[str] = []
        current = ""
        for line in lines:
            candidate = f"{current}\n{line}".strip()
            if len(candidate) > max_chars and current:
                chunks.append(current)
                current = line
            else:
                current = candidate
        if current:
            chunks.append(current)
        return chunks

    async def example_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        args = [str(arg).strip().lower() for arg in (context.args or []) if str(arg).strip()]
        requested_topic = args[0] if args else "overview"

        available_topics = sorted(_EXAMPLE_PROMPTS.keys())
        if requested_topic == "overview":
            lines = [
                "🧭 HER Examples",
                "Use: /example <topic>",
                "Use: /example all",
                f"Topics: {', '.join(available_topics)}",
                "",
                "Try these now:",
            ]
            seed_examples = (
                _EXAMPLE_PROMPTS["chat"][:2]
                + _EXAMPLE_PROMPTS["scheduling"][:2]
                + _EXAMPLE_PROMPTS["automation"][:2]
            )
            for sample in seed_examples:
                lines.append(f"- {sample}")
            lines.append("")
            lines.append("Full library: docs/examples.md")
            await self._reply(update, "\n".join(lines))
            return

        if requested_topic == "all":
            lines = ["📚 Full Example Library (/example all)"]
            for topic in available_topics:
                lines.append("")
                lines.append(f"[{topic}]")
                for idx, prompt in enumerate(_EXAMPLE_PROMPTS[topic], start=1):
                    lines.append(f"{idx}. {prompt}")
            lines.append("")
            lines.append("More: docs/examples.md")
            for chunk in self._chunk_lines(lines):
                await self._reply(update, chunk)
            return

        if requested_topic not in _EXAMPLE_PROMPTS:
            await self._reply(
                update,
                f"Unknown topic '{requested_topic}'. Available: {', '.join(available_topics)}",
            )
            return

        topic_lines = [f"🧩 Examples: {requested_topic}"]
        for idx, prompt in enumerate(_EXAMPLE_PROMPTS[requested_topic], start=1):
            topic_lines.append(f"{idx}. {prompt}")
        topic_lines.append("")
        topic_lines.append("More topics: /example overview")
        topic_lines.append("Full library: docs/examples.md")
        await self._reply(update, "\n".join(topic_lines))

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_admin(update.effective_user.id):
            await self._reply(update, "❌ Admin only command")
            return

        status_lines = ["📊 HER Status"]
        if self.mcp_manager:
            mcp_status = self.mcp_manager.get_server_status()
            status_lines.append(f"MCP: {mcp_status}")
        await self._reply(update, "\n".join(status_lines))

    async def personality_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_admin(update.effective_user.id):
            await self._reply(update, "❌ Admin only command")
            return
        await self._reply(update, "Adjust personality traits:", reply_markup=get_personality_adjustment())

    async def memories_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_admin(update.effective_user.id):
            await self._reply(update, "❌ Admin only command")
            return

        user_id = str(update.effective_user.id)
        context_messages = self.memory.get_context(user_id)
        await self._reply(update, f"Recent context entries: {len(context_messages)}")

    async def reflect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_admin(update.effective_user.id):
            await self._reply(update, "❌ Admin only command")
            return
        await self._reply(update, "🔄 Reflection triggered (placeholder)")

    async def reset_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_admin(update.effective_user.id):
            await self._reply(update, "❌ Admin only command")
            return
        self.rate_limiter.reset_user(update.effective_user.id)
        await self._reply(update, "🗑️ Context reset complete (rate-limit bucket reset).")

    async def mcp_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_admin(update.effective_user.id):
            await self._reply(update, "❌ Admin only command")
            return
        status = self.mcp_manager.get_server_status() if self.mcp_manager else {"mcp": "not configured"}
        await self._reply(update, f"🔧 MCP status:\n{status}")

    async def schedule_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_admin(update.effective_user.id):
            await self._reply(update, "❌ Admin only command")
            return
        if not self.scheduler:
            await self._reply(update, "❌ Scheduler not initialized")
            return

        args = [str(arg).strip() for arg in (context.args or []) if str(arg).strip()]
        action = args[0].lower() if args else "list"

        if action in {"list", "show"}:
            tasks = self.scheduler.get_tasks()
            if not tasks:
                await self._reply(update, "⏰ No scheduled tasks configured.")
                return
            task_lines = []
            for task in tasks:
                name = task.get("name", "unknown")
                task_type = task.get("type", "custom")
                interval = task.get("interval", "unknown")
                enabled = "on" if task.get("enabled", True) else "off"
                next_run = task.get("_next_run", "pending")
                at_value = task.get("at")
                suffix = f" | at={at_value}" if at_value else ""
                task_lines.append(
                    f"- {name} | type={task_type} | interval={interval} | enabled={enabled} | next={next_run}{suffix}"
                )
            usage_lines = [
                "/schedule set <task> <interval>",
                "/schedule enable <task> | /schedule disable <task>",
                "/schedule run <task>",
                "/schedule add <name> <type> <interval> [key=value ...]",
                "",
                "Reminder example:",
                "/schedule add stretch reminder daily at=09:00 timezone=UTC message='Take a short stretch break' notify_user_id=123456789",
                "",
                "Workflow example:",
                "/schedule add any_rule workflow every_5_minutes source_url=https://example/api steps_json='[{\"action\":\"log\",\"message\":\"tick {now_utc}\"}]'",
            ]
            message = (
                "*⏰ Scheduled Tasks*\n"
                "```text\n"
                + "\n".join(task_lines)
                + "\n```\n\n"
                "*Usage*\n"
                "```text\n"
                + "\n".join(usage_lines)
                + "\n```"
            )
            await self._reply_markdown(update, message)
            return

        if action == "set":
            if len(args) < 3:
                await self._reply(update, "Usage: /schedule set <task_name> <interval>")
                return
            task_name = args[1]
            interval = args[2].lower()
            try:
                updated = self.scheduler.set_task_interval(task_name, interval)
            except ValueError as exc:
                await self._reply(update, f"❌ {exc}")
                return
            if not updated:
                await self._reply(update, f"❌ Task '{task_name}' not found")
                return
            ok, details = self.scheduler.persist_tasks()
            status = "saved" if ok else "not saved"
            self._decision_logger.log(
                event_type="schedule_interval_update",
                summary=f"Updated task '{task_name}' interval to '{interval}'",
                user_id=str(update.effective_user.id),
                source="telegram",
                details={"task": task_name, "interval": interval, "saved": ok, "details": details},
            )
            await self._reply(update, f"✅ Updated '{task_name}' interval to '{interval}' ({status}: {details})")
            return

        if action in {"enable", "disable"}:
            if len(args) < 2:
                await self._reply(update, f"Usage: /schedule {action} <task_name>")
                return
            task_name = args[1]
            enabled = action == "enable"
            updated = self.scheduler.set_task_enabled(task_name, enabled)
            if not updated:
                await self._reply(update, f"❌ Task '{task_name}' not found")
                return
            ok, details = self.scheduler.persist_tasks()
            state = "enabled" if enabled else "disabled"
            status = "saved" if ok else "not saved"
            self._decision_logger.log(
                event_type="schedule_toggle",
                summary=f"Task '{task_name}' {state}",
                user_id=str(update.effective_user.id),
                source="telegram",
                details={"task": task_name, "enabled": enabled, "saved": ok, "details": details},
            )
            await self._reply(update, f"✅ Task '{task_name}' {state} ({status}: {details})")
            return

        if action == "run":
            if len(args) < 2:
                await self._reply(update, "Usage: /schedule run <task_name>")
                return
            task_name = args[1]
            ok, details = await self.scheduler.run_task_now(task_name)
            if not ok:
                await self._reply(update, f"❌ {details}: '{task_name}'")
                return
            self._decision_logger.log(
                event_type="schedule_run_now",
                summary=f"Ran task '{task_name}' immediately",
                user_id=str(update.effective_user.id),
                source="telegram",
                details={"task": task_name},
            )
            await self._reply(update, f"✅ Task '{task_name}' executed now")
            return

        if action == "add":
            if len(args) < 4:
                await self._reply(update, "Usage: /schedule add <name> <type> <interval> [key=value ...]")
                return
            name, task_type, interval = args[1], args[2], args[3].lower()
            existing_names = {str(t.get('name')) for t in self.scheduler.get_tasks()}
            if name in existing_names:
                await self._reply(update, f"❌ Task '{name}' already exists")
                return
            extra_args: dict[str, Any] = {}
            for token in args[4:]:
                if "=" not in token:
                    continue
                key, raw_value = token.split("=", 1)
                key = key.strip()
                value_text = raw_value.strip()
                if (value_text.startswith("'") and value_text.endswith("'")) or (
                    value_text.startswith('"') and value_text.endswith('"')
                ):
                    value_text = value_text[1:-1]
                lowered = value_text.lower()
                if key.endswith("_json"):
                    parsed_key = key[: -len("_json")] or key
                    try:
                        extra_args[parsed_key] = json.loads(value_text)
                    except json.JSONDecodeError:
                        await self._reply(update, f"❌ Invalid JSON for '{key}'")
                        return
                    continue
                if lowered in {"true", "false"}:
                    parsed_value: Any = lowered == "true"
                else:
                    try:
                        if "." in value_text:
                            parsed_value = float(value_text)
                        else:
                            parsed_value = int(value_text)
                    except ValueError:
                        parsed_value = value_text
                if key:
                    extra_args[key] = parsed_value

            if task_type == "workflow" and "notify_user_id" not in extra_args:
                extra_args["notify_user_id"] = update.effective_user.id
            try:
                self.scheduler.add_task(
                    name=name,
                    task_type=task_type,
                    interval=interval,
                    enabled=True,
                    **extra_args,
                )
            except ValueError as exc:
                await self._reply(update, f"❌ {exc}")
                return
            ok, details = self.scheduler.persist_tasks()
            status = "saved" if ok else "not saved"
            self._decision_logger.log(
                event_type="schedule_add",
                summary=f"Added schedule task '{name}'",
                user_id=str(update.effective_user.id),
                source="telegram",
                details={"task": name, "type": task_type, "interval": interval, "saved": ok, "details": details},
            )
            await self._reply(update, f"✅ Added task '{name}' ({status}: {details})")
            return

        await self._reply(
            update,
            "Unknown schedule action. Use: list|set|enable|disable|run|add",
        )

    def _fetch_online_utc_now(self) -> datetime | None:
        try:
            with urlopen("https://worldtimeapi.org/api/timezone/Etc/UTC", timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
            utc_datetime = payload.get("utc_datetime")
            if not utc_datetime:
                return None
            return datetime.fromisoformat(utc_datetime.replace("Z", "+00:00")).astimezone(UTC)
        except (URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            logger.debug("UTC time lookup failed: %s", exc)
            return None

    def _fetch_btc_price_usd(self) -> float | None:
        endpoints = [
            ("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd", lambda p: p.get("bitcoin", {}).get("usd")),
            ("https://api.coinbase.com/v2/prices/BTC-USD/spot", lambda p: p.get("data", {}).get("amount")),
        ]
        for endpoint, extractor in endpoints:
            try:
                with urlopen(endpoint, timeout=10) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                usd_price = extractor(payload)
                if usd_price is not None:
                    return float(usd_price)
            except (URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
                logger.debug("BTC price lookup failed for %s: %s", endpoint, exc)
        return None

    def _maybe_answer_realtime_query(self, message: str) -> str | None:
        lower_msg = message.lower()
        online_utc = self._fetch_online_utc_now()
        now_utc = online_utc or datetime.now(UTC)
        time_source = "WorldTimeAPI" if online_utc else "system clock"

        date_tokens = {"date", "today", "what day", "which day", "day today"}
        time_tokens = {"time now", "current time", "what time", "now time", "utc"}
        asks_date = any(token in lower_msg for token in date_tokens)
        asks_time = any(token in lower_msg for token in time_tokens)

        if asks_date or asks_time:
            return (
                f"Right now (UTC): {now_utc.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Today is {now_utc.strftime('%A, %d %B %Y')} (UTC).\n"
                f"Source: {time_source}."
            )

        if any(token in lower_msg for token in {"bitcoin", "btc"}):
            usd_price = self._fetch_btc_price_usd()
            if usd_price is not None:
                return (
                    f"Live BTC price: ${usd_price:,.2f} USD.\n"
                    f"Timestamp (UTC): {now_utc.strftime('%Y-%m-%d %H:%M:%S')}"
                )

            search_result = self._web_search_tool._run("BTC USD price now", max_results=1)
            if not search_result.lower().startswith("web search failed"):
                return f"I could not reach pricing APIs, but web search found:\n{search_result}"

        return None

    @staticmethod
    def _wants_utc_timestamp(message: str) -> bool:
        lower_msg = message.lower()
        explicit_phrases = {
            "utc time",
            "time in utc",
            "utc timestamp",
            "timestamp utc",
            "tell me utc",
            "include utc time",
        }
        if any(phrase in lower_msg for phrase in explicit_phrases):
            return True
        return "utc" in lower_msg and ("time" in lower_msg or "timestamp" in lower_msg)

    def _format_current_utc_line(self) -> str:
        now_utc = self._fetch_online_utc_now() or datetime.now(UTC)
        return f"Timestamp (UTC): {now_utc.strftime('%Y-%m-%d %H:%M:%S')}"

    @staticmethod
    def _extract_scan_target(message: str) -> str | None:
        match = _HOST_PATTERN.search(message)
        if not match:
            return None
        return match.group(1).strip().lower()

    def _sandbox_capability(self) -> tuple[bool, str]:
        caps = self._get_runtime_capabilities()
        if not caps:
            return True, "runtime capability snapshot missing; allowing sandbox by default"
        sandbox = (caps.get("capabilities", {}) or {}).get("sandbox", {}) if caps else {}
        available = bool(sandbox.get("available", True))
        reason = str(sandbox.get("reason", "unknown"))
        return available, reason

    def _maybe_answer_sandbox_security_query(self, message: str) -> str | None:
        lower_msg = message.lower()
        is_scan_intent = any(
            token in lower_msg
            for token in {
                "port scan",
                "nmap",
                "security scan",
                "scan host",
                "scan website",
                "dns lookup",
                "traceroute",
                "ssl",
                "certificate",
            }
        )
        if not is_scan_intent:
            return None

        target = self._extract_scan_target(message)
        if not target:
            return "Please provide a host or domain to scan (example: vaheed.net)."

        sandbox_ok, sandbox_reason = self._sandbox_capability()
        if not sandbox_ok:
            return (
                "Sandbox security tools are currently unavailable, so I cannot run the scan now.\n"
                f"Reason: {sandbox_reason}"
            )

        container_name = os.getenv("SANDBOX_CONTAINER_NAME", "her-sandbox")
        try:
            if "port scan" in lower_msg or "nmap" in lower_msg:
                result = SandboxNetworkTool(container_name=container_name)._run(
                    target=target,
                    action="port_scan",
                    ports="1-1024",
                    timeout=60,
                )
                return f"Port scan summary for {target}:\n{result}"
            if "dns" in lower_msg:
                result = SandboxNetworkTool(container_name=container_name)._run(
                    target=target,
                    action="dns",
                    timeout=45,
                )
                return f"DNS lookup summary for {target}:\n{result}"
            if "traceroute" in lower_msg:
                result = SandboxNetworkTool(container_name=container_name)._run(
                    target=target,
                    action="traceroute",
                    timeout=60,
                )
                return f"Traceroute summary for {target}:\n{result}"
            if "ssl" in lower_msg or "certificate" in lower_msg:
                result = SandboxNetworkTool(container_name=container_name)._run(
                    target=target,
                    action="ssl",
                    timeout=60,
                )
                return f"SSL/TLS summary for {target}:\n{result}"

            # Default security baseline scan.
            mode = "website" if message.lower().find("http://") != -1 or message.lower().find("https://") != -1 else "host"
            result = SandboxSecurityScanTool(container_name=container_name)._run(
                target=target,
                mode=mode,
                timeout=90,
            )
            return f"Security scan summary for {target}:\n{result}"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Sandbox security query failed for target '%s': %s", target, exc)
            return f"Sandbox scan failed for {target}: {exc}"

    def _is_group_chat(self, update: Update) -> bool:
        chat_type = (update.effective_chat.type or "") if update.effective_chat else ""
        return chat_type in {"group", "supergroup"}

    def _group_memory_key(self, chat_id: int) -> str:
        return f"group:{chat_id}"

    def _message_mentions_bot(self, update: Update) -> bool:
        message = update.message
        if not message:
            return False

        if message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.is_bot:
            return True

        text = message.text or ""
        entities = message.entities or []
        for entity in entities:
            if entity.type in {MessageEntity.MENTION, MessageEntity.TEXT_MENTION}:
                mention_text = text[entity.offset : entity.offset + entity.length].lower()
                if self.bot_username and self.bot_username in mention_text:
                    return True

        if self.bot_username and f"@{self.bot_username}" in text.lower():
            return True

        return False

    async def _summarize_group_if_needed(self, chat_id: int) -> None:
        group_key = self._group_memory_key(chat_id)
        context_messages = self.memory.get_context(group_key)
        if not context_messages:
            return
        if len(context_messages) % self.group_summary_every_messages != 0:
            return

        recent = context_messages[-self.group_summary_every_messages :]
        transcript = "\n".join(f"- {item.get('role')}: {item.get('message')}" for item in recent)
        prompt = (
            "Summarize this group chat snippet for long-term memory. "
            "Return 3-5 bullet points with durable preferences, commitments, important decisions, and names."
            " Skip small talk."
            f"\n\n{transcript}"
        )

        try:
            summary_text, _ = self._generate_response_with_failover(
                [
                    SystemMessage(content="You extract durable memory summaries from chats."),
                    HumanMessage(content=prompt),
                ],
                chat_id,
            )
            if summary_text:
                self.memory.add_memory(group_key, summary_text, "group_summary", 0.9)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to summarize group chat %s: %s", chat_id, exc)

    def _extract_memories_from_message(self, text: str) -> list[dict[str, Any]]:
        if not self.reflection_agent:
            return []
        try:
            raw = self.reflection_agent.analyze_conversation([{"role": "user", "message": text}])
            if not isinstance(raw, list):
                return []
            normalized: list[dict[str, Any]] = []
            for item in raw:
                if not isinstance(item, dict):
                    continue
                text_value = item.get("text", "")
                if isinstance(text_value, list):
                    text_value = " ".join(str(v) for v in text_value if v is not None)
                text_value = str(text_value).strip()
                if not text_value:
                    continue
                category = str(item.get("category", "general")).strip() or "general"
                try:
                    importance = float(item.get("importance", 0.6))
                except (TypeError, ValueError):
                    importance = 0.6
                normalized.append(
                    {
                        "text": text_value,
                        "category": category,
                        "importance": max(0.0, min(1.0, importance)),
                    }
                )
            return normalized
        except Exception as exc:  # noqa: BLE001
            logger.debug("Reflection extraction skipped: %s", exc)
            return []

    @staticmethod
    def _slug(text: str, max_len: int = 48) -> str:
        clean = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
        if not clean:
            clean = "task"
        return clean[:max_len]

    @staticmethod
    def _parse_clock(text: str) -> tuple[int, int] | None:
        return parse_clock(text)

    @staticmethod
    def _extract_reminder_body(message: str) -> str:
        text = message.strip()
        lowered = text.lower()
        patterns = [
            r"remind me to\s+(.+)",
            r"remind me\s+(.+)",
            r"remember to\s+(.+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, lowered, re.IGNORECASE)
            if match:
                start = match.start(1)
                body = text[start:].strip(" .")
                body = re.sub(
                    r"\s+((?:in|after)\s+\d+\s*(?:m|min|mins|minutes?|h|hr|hrs|hours?|d|days?)|tomorrow(?:\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)?|"
                    r"next\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)(?:\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)?|"
                    r"every\s+\d+\s*(?:m|min|mins|minutes?|h|hr|hrs|hours?|d|days?)|every day|daily|once a week|every week|weekly)\b.*$",
                    "",
                    body,
                    flags=re.IGNORECASE,
                ).strip(" .")
                return body or "your reminder"
        return text[:220]

    @staticmethod
    def _interval_unit_to_base(unit: str) -> str:
        return interval_unit_to_base(unit)

    def _looks_like_scheduling_intent(self, message: str) -> bool:
        lower = message.lower()
        markers = (
            "remind",
            "remember",
            "schedule",
            "notify me",
            "alert me",
            "every ",
            "in ",
            "after ",
            "tomorrow",
            "next ",
            "at ",
            "daily",
            "weekly",
            "hourly",
        )
        return any(marker in lower for marker in markers)

    @staticmethod
    def _extract_json_object(raw: str) -> dict[str, Any] | None:
        return extract_json_object(raw)

    @staticmethod
    def _normalize_weekdays_input(raw: Any) -> list[int]:
        return normalize_weekdays_input(raw)

    @staticmethod
    def _history_for_llm(context_rows: list[dict[str, Any]], limit: int = 200) -> str:
        rows = context_rows[-max(1, int(limit)) :]
        lines: list[str] = []
        for row in rows:
            role = str(row.get("role", "user"))
            message = str(row.get("message", "")).strip()
            if message:
                lines.append(f"{role}: {message}")
        return "\n".join(lines) if lines else "(none)"

    @staticmethod
    def _detect_language_heuristic(message: str) -> str:
        text = message.strip()
        if not text:
            return "en"
        if re.search(r"[\u0600-\u06FF]", text):
            return "fa"
        if re.search(r"[\u4E00-\u9FFF]", text):
            return "zh"
        if re.search(r"[\u3040-\u30FF]", text):
            return "ja"
        if re.search(r"[\uAC00-\uD7AF]", text):
            return "ko"
        if re.search(r"[\u0400-\u04FF]", text):
            return "ru"
        if re.search(r"[ñáéíóúü¿¡]", text.lower()):
            return "es"
        return "en"

    def _detect_user_language(self, message: str, user_id: int, context_rows: list[dict[str, Any]]) -> str:
        now_ts = time.time()
        cached = self._language_cache.get(user_id)
        if cached and now_ts - cached[1] <= 1800:
            return cached[0]

        heuristic = self._detect_language_heuristic(message)
        if heuristic != "en":
            self._language_cache[user_id] = (heuristic, now_ts)
            return heuristic
        # Avoid expensive LLM calls for clear/long English messages.
        if len(message.strip()) >= 24:
            self._language_cache[user_id] = (heuristic, now_ts)
            return heuristic

        history_text = self._history_for_llm(context_rows, limit=60)
        prompt = (
            "Detect the language of the latest user message.\n"
            "Return JSON only:\n"
            '{ "language": "ISO-639-1 code" }\n'
            "Use recent context only to resolve ambiguous short text.\n\n"
            f"Conversation history:\n{history_text}\n\n"
            f"Latest user message:\n{message}"
        )
        llm_messages = [
            SystemMessage(content="You are a language detector. Return strict JSON only."),
            HumanMessage(content=prompt),
        ]
        try:
            response_text, _ = self._generate_response_with_failover(llm_messages, user_id)
            payload = self._extract_json_object(response_text)
            language = str((payload or {}).get("language", "")).strip().lower()
            if re.match(r"^[a-z]{2}$", language):
                self._language_cache[user_id] = (language, now_ts)
                return language
        except Exception as exc:  # noqa: BLE001
            logger.debug("Language detection via LLM failed for user %s: %s", user_id, exc)
        self._language_cache[user_id] = (heuristic, now_ts)
        return heuristic

    def _build_scheduler_confirmation(
        self,
        user_id: int,
        language: str,
        original_request: str,
        task: dict[str, Any],
        context_rows: list[dict[str, Any]],
    ) -> str:
        time_reference = "unspecified time"
        if str(task.get("interval", "")).lower() == "once":
            run_at = str(task.get("run_at", "")).strip()
            if run_at:
                time_reference = run_at
        elif task.get("at"):
            tz = str(task.get("timezone", "UTC")).strip() or "UTC"
            time_reference = f"{task.get('at')} ({tz})"
        else:
            time_reference = str(task.get("interval", "scheduled")).replace("_", " ")

        history_text = self._history_for_llm(context_rows, limit=80)
        prompt = (
            "Write one natural scheduler confirmation sentence.\n"
            "Rules:\n"
            f"- Language must be: {language}\n"
            "- Mention the original user request naturally.\n"
            "- Include a clear time reference.\n"
            "- Keep conversational continuity with recent history.\n"
            "- No markdown.\n\n"
            f"Recent conversation:\n{history_text}\n\n"
            f"Original request: {original_request}\n"
            f"Task name: {task.get('name', '')}\n"
            f"Task type: {task.get('type', 'reminder')}\n"
            f"Time reference: {time_reference}"
        )
        llm_messages = [
            SystemMessage(content="You generate short scheduling confirmations. Return plain text only."),
            HumanMessage(content=prompt),
        ]
        try:
            response_text, _ = self._generate_response_with_failover(llm_messages, user_id)
            confirmation = str(response_text or "").strip()
            if confirmation:
                return f"✅ {confirmation}"
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to generate localized scheduler confirmation for user %s: %s", user_id, exc)
        fallback_prompt = (
            "Translate this short confirmation to language code "
            f"{language} and keep the same meaning.\n"
            "Return plain text only.\n"
            f"Text: Scheduled your request for {time_reference}."
        )
        try:
            response_text, _ = self._generate_response_with_failover(
                [
                    SystemMessage(content="You are a translator."),
                    HumanMessage(content=fallback_prompt),
                ],
                user_id,
            )
            translated = str(response_text or "").strip()
            if translated:
                return f"✅ {translated}"
        except Exception:  # noqa: BLE001
            pass
        return f"✅ Scheduled your request for {time_reference}."

    def _render_in_user_language(self, user_id: int, language: str, text: str) -> str:
        prompt = (
            f"Rewrite the following text in language code {language}.\n"
            "Keep meaning and tone, return plain text only.\n"
            f"Text: {text}"
        )
        try:
            response_text, _ = self._generate_response_with_failover(
                [
                    SystemMessage(content="You are a translator and rewriter."),
                    HumanMessage(content=prompt),
                ],
                user_id,
            )
            rewritten = str(response_text or "").strip()
            if rewritten:
                return rewritten
        except Exception as exc:  # noqa: BLE001
            logger.debug("Language rendering failed for user %s: %s", user_id, exc)
        return text

    def _parse_multi_intent_schedule_with_llm(
        self,
        message: str,
        user_id: int,
        chat_id: int | None,
        user_timezone: str,
        language: str,
        context_rows: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], str]:
        if not self.scheduler:
            return [], message

        now_utc = datetime.now(UTC)
        history_text = self._history_for_llm(context_rows, limit=200)
        prompt = (
            "Analyze the latest user message with full conversation context.\n"
            "Extract ALL scheduling/reminder/workflow intents sequentially.\n"
            "If message is a short follow-up command after prior planning/scheduling (example: 'call Ali'), "
            "treat it as a new actionable scheduling task.\n"
            "Return JSON only:\n"
            "{\n"
            '  "tasks": [\n'
            "    {\n"
            '      "name": "optional",\n'
            '      "type": "reminder|workflow|custom",\n'
            '      "interval": "once|hourly|daily|weekly|every_<N>_minutes|every_<N>_hours|every_<N>_days",\n'
            '      "run_at": "ISO8601 optional",\n'
            '      "at": "HH:MM optional",\n'
            '      "timezone": "IANA timezone optional",\n'
            '      "weekdays": [0-6 optional],\n'
            '      "message": "reminder message optional",\n'
            '      "notify_user_id": 0,\n'
            '      "max_retries": 2,\n'
            '      "retry_delay_seconds": 30,\n'
            '      "steps": []\n'
            "    }\n"
            "  ],\n"
            '  "remaining_request": "non-scheduling remainder or empty string"\n'
            "}\n"
            "Rules:\n"
            f"- Response language context is {language}.\n"
            f"- User timezone is {self._safe_timezone_name(user_timezone)}.\n"
            "- Keep tasks in user-intended order.\n"
            "- For short imperative follow-ups with no time, default to once with run_at ~5 minutes from now.\n"
            "- Reminder tasks must include a valid chat target; keep notify_user_id aligned with this user.\n"
            "- If the whole message is scheduling, set remaining_request to empty string.\n\n"
            f"Current UTC time: {now_utc.isoformat()}\n"
            f"Conversation history:\n{history_text}\n\n"
            f"Latest user message:\n{message}"
        )
        llm_messages = [
            SystemMessage(content="You are a deterministic scheduler intent extractor. Return JSON only."),
            HumanMessage(content=prompt),
        ]
        try:
            response_text, _ = self._generate_response_with_failover(llm_messages, user_id)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Multi-intent schedule parser unavailable for user %s: %s", user_id, exc)
            return [], message

        payload = self._extract_json_object(response_text)
        if not payload:
            return [], message

        raw_tasks = payload.get("tasks")
        remaining_request = str(payload.get("remaining_request", message)).strip()
        if not isinstance(raw_tasks, list):
            return [], message

        normalized_tasks: list[dict[str, Any]] = []
        for raw_task in raw_tasks:
            try:
                task = self._normalize_ai_schedule_task(raw_task, user_id, chat_id, user_timezone, message, now_utc)
                if task:
                    normalized_tasks.append(task)
            except ValueError as exc:
                logger.debug("Skipping invalid schedule task for user %s: %s", user_id, exc)

        return normalized_tasks, remaining_request

    def _normalize_ai_schedule_task(
        self,
        task: Any,
        user_id: int,
        chat_id: int | None,
        user_timezone: str,
        source_message: str,
        now_utc: datetime,
    ) -> dict[str, Any] | None:
        if not isinstance(task, dict) or not self.scheduler:
            return None

        interval = str(task.get("interval", "")).strip().lower()
        if not self.scheduler.is_valid_interval(interval):
            return None

        task_type = str(task.get("type", "reminder")).strip().lower() or "reminder"
        if task_type not in {"reminder", "workflow", "custom"}:
            task_type = "reminder"

        name_raw = str(task.get("name", "")).strip()
        if name_raw:
            task_name = self._slug(name_raw, max_len=56)
        else:
            task_name = f"nl_{self._slug(source_message)}_{user_id}"

        normalized: dict[str, Any] = {
            "name": task_name,
            "type": task_type,
            "interval": interval,
            "enabled": bool(task.get("enabled", True)),
            "one_time": bool(task.get("one_time", interval == "once")),
            "max_retries": max(0, int(task.get("max_retries", 2) or 2)),
            "retry_delay_seconds": max(1, int(task.get("retry_delay_seconds", 30) or 30)),
        }

        notify_user_id = task.get("notify_user_id")
        parsed_notify_user_id: int | None = None
        if isinstance(notify_user_id, int):
            parsed_notify_user_id = notify_user_id
        elif str(notify_user_id or "").strip().isdigit():
            parsed_notify_user_id = int(str(notify_user_id).strip())

        if parsed_notify_user_id is not None and parsed_notify_user_id > 0:
            normalized["notify_user_id"] = parsed_notify_user_id
        else:
            normalized["notify_user_id"] = user_id

        if task_type == "reminder":
            resolved_chat_id = self._resolve_reminder_chat_id(user_id, chat_id)
            if resolved_chat_id is None:
                raise ValueError("Chat ID required for reminders")
            normalized["chat_id"] = resolved_chat_id
            normalized["status"] = "PENDING"
            normalized["retry_count"] = 0
            normalized["max_retries"] = max(1, int(task.get("max_retries", 3) or 3))
            normalized["last_error"] = ""

        run_at = str(task.get("run_at", "")).strip()
        if run_at:
            try:
                run_at_dt = datetime.fromisoformat(run_at.replace("Z", "+00:00"))
                if run_at_dt.tzinfo is None:
                    run_at_dt = run_at_dt.replace(tzinfo=ZoneInfo(user_timezone))
                run_at_utc = run_at_dt.astimezone(UTC)
                normalized["run_at"] = run_at_utc.isoformat()
                self._log_timezone_conversion(user_id, user_timezone, run_at_dt.isoformat(), run_at_utc.isoformat())
            except ValueError:
                if interval == "once":
                    normalized["run_at"] = (now_utc + timedelta(minutes=5)).isoformat()

        at_value = str(task.get("at", "")).strip()
        if at_value and re.match(r"^\d{2}:\d{2}$", at_value):
            hour, minute = at_value.split(":", 1)
            if 0 <= int(hour) <= 23 and 0 <= int(minute) <= 59:
                normalized["at"] = at_value

        timezone_value = self._safe_timezone_name(str(task.get("timezone", user_timezone)))
        normalized["timezone"] = timezone_value
        normalized["user_timezone"] = user_timezone

        weekdays = self._normalize_weekdays_input(task.get("weekdays"))
        if weekdays:
            normalized["weekdays"] = weekdays

        message_text = str(task.get("message", "")).strip()
        if task_type == "reminder":
            normalized["message"] = message_text or self._extract_reminder_body(source_message) or "Reminder"

        if task_type == "workflow":
            steps = task.get("steps")
            if not isinstance(steps, list) or not steps:
                return None
            filtered_steps = [item for item in steps if isinstance(item, dict)]
            if not filtered_steps:
                return None
            normalized["steps"] = filtered_steps
            source_url = str(task.get("source_url", "")).strip()
            if source_url:
                normalized["source_url"] = source_url
            condition_expr = str(task.get("condition_expr", "")).strip()
            if condition_expr:
                normalized["condition_expr"] = condition_expr

        return normalized

    def _parse_schedule_request_with_llm(
        self,
        message: str,
        user_id: int,
        chat_id: int | None,
        user_timezone: str,
    ) -> tuple[dict[str, Any] | None, str | None]:
        if not self.scheduler:
            return None, None
        if not self._looks_like_scheduling_intent(message):
            return None, None

        now_utc = datetime.now(UTC)
        prompt = (
            "Convert this user message into ONE scheduler task for a Telegram assistant.\n"
            "Current UTC time: "
            f"{now_utc.isoformat()}\n"
            f"User timezone: {self._safe_timezone_name(user_timezone)}\n"
            "Return strict JSON only (no markdown) with this schema:\n"
            "{\n"
            '  "create_task": boolean,\n'
            '  "confirmation": "short human confirmation",\n'
            '  "task": {\n'
            '    "name": "short_name_optional",\n'
            '    "type": "reminder|workflow|custom",\n'
            '    "interval": "once|hourly|daily|weekly|every_<N>_minutes|every_<N>_hours|every_<N>_days",\n'
            '    "run_at": "ISO8601 optional for one-time",\n'
            '    "at": "HH:MM optional",\n'
            '    "timezone": "IANA timezone optional",\n'
            '    "weekdays": [0-6 optional],\n'
            '    "message": "for reminder tasks",\n'
            '    "notify_user_id": 0,\n'
            '    "source_url": "optional for workflows",\n'
            '    "condition_expr": "optional python-like expression",\n'
            '    "steps": [{"action":"set|set_state|notify|fetch_json|log|webhook", "key":"...", "expr":"...", "when":"...", "message":"..."}]\n'
            "  }\n"
            "}\n"
            "Rules:\n"
            "- If message is not a scheduling request, return {\"create_task\": false}.\n"
            "- Keep task safe and minimal.\n"
            "- For one-time reminders like 'in 5 minutes', provide run_at in user timezone or UTC.\n"
            "- For thresholds/automation conditions, use type=workflow with steps.\n"
            "- In workflow expressions (when/expr/condition_expr), reference only defined names: "
            "source, state, task, task_name, now_utc, or keys set by earlier steps.\n"
            "- For 'rises X% from current price' requests, store the baseline in state and compare "
            "current values against state baseline using state.get(...).\n"
            f"User message: {message}"
        )

        llm_messages = [
            SystemMessage(
                content=(
                    "You convert natural-language scheduling requests to strict JSON for a task scheduler. "
                    "Return JSON only."
                )
            ),
            HumanMessage(content=prompt),
        ]
        try:
            response_text, _ = self._generate_response_with_failover(llm_messages, user_id)
        except Exception as exc:  # noqa: BLE001
            logger.debug("LLM schedule parser unavailable for user %s: %s", user_id, exc)
            return None, None

        payload = self._extract_json_object(response_text)
        if not payload:
            return None, None
        if not bool(payload.get("create_task")):
            return None, None

        try:
            normalized_task = self._normalize_ai_schedule_task(
                payload.get("task"),
                user_id,
                chat_id,
                user_timezone,
                message,
                now_utc,
            )
        except ValueError:
            return None, None
        if not normalized_task:
            return None, None

        confirmation = str(payload.get("confirmation", "")).strip() or "Got it. I scheduled that."
        return normalized_task, confirmation

    def _goal_growth_intent(self, message: str) -> bool:
        lower = message.lower()
        phrases = [
            "help me grow",
            "improve me",
            "track my habits",
            "keep me accountable",
            "build better habits",
            "help me improve",
        ]
        return any(phrase in lower for phrase in phrases)

    def _parse_schedule_request(
        self,
        message: str,
        user_id: int,
        chat_id: int | None,
        user_timezone: str,
    ) -> tuple[dict[str, Any] | None, str | None]:
        if not self.scheduler:
            return None, None

        # Legacy call path reference: self._parse_schedule_request_with_llm(message, user_id)
        llm_task, llm_confirmation = self._parse_schedule_request_with_llm(
            message,
            user_id,
            chat_id,
            user_timezone,
        )
        if llm_task and llm_confirmation:
            return llm_task, llm_confirmation

        text = message.strip()
        lower = text.lower()
        local_tz = ZoneInfo(self._safe_timezone_name(user_timezone))
        now_local = datetime.now(local_tz)
        now = now_local.astimezone(UTC)
        reminder_body = self._extract_reminder_body(text)
        clock = self._parse_clock(text) or (9, 0)
        future_intent = any(
            marker in lower for marker in ("remind", "remember", "schedule", "i need to", "i should", "don't let me forget")
        )

        # Goal-oriented recurring automation
        if self._goal_growth_intent(text):
            task_name = f"growth_checkin_{user_id}"
            return (
                {
                    "name": task_name,
                    "type": "workflow",
                    "interval": "daily",
                    "enabled": True,
                    "at": "20:00",
                    "timezone": self._safe_timezone_name(user_timezone),
                    "notify_user_id": user_id,
                    "steps": [
                        {"action": "notify", "message": "Growth check-in: what improved today and what needs support?"},
                        {"action": "log", "message": "growth check-in delivered to {task_name}"},
                    ],
                    "max_retries": 2,
                    "retry_delay_seconds": 30,
                },
                "Got it. I'll run a daily growth check-in and help you track progress.",
            )

        # every N minutes/hours/days
        every_match = _EVERY_INTERVAL_PATTERN.search(lower)
        if every_match:
            value = int(every_match.group(1))
            unit = every_match.group(2)
            base = self._interval_unit_to_base(unit)
            interval = f"every_{max(1, value)}_{base}"
            task_name = f"auto_{self._slug(reminder_body)}_{user_id}"
            return (
                {
                    "name": task_name,
                    "type": "reminder",
                    "interval": interval,
                    "enabled": True,
                    "timezone": self._safe_timezone_name(user_timezone),
                    "user_timezone": self._safe_timezone_name(user_timezone),
                    "message": reminder_body,
                    "chat_id": self._resolve_reminder_chat_id(user_id, chat_id),
                    "status": "PENDING",
                    "retry_count": 0,
                    "last_error": "",
                    "notify_user_id": user_id,
                    "max_retries": 3,
                    "retry_delay_seconds": 30,
                },
                f"Got it. I'll remind you {interval.replace('_', ' ')}.",
            )

        # every day / daily
        if "every day" in lower or "daily" in lower:
            task_name = f"daily_{self._slug(reminder_body)}_{user_id}"
            return (
                {
                    "name": task_name,
                    "type": "reminder",
                    "interval": "daily",
                    "enabled": True,
                    "at": f"{clock[0]:02d}:{clock[1]:02d}",
                    "timezone": self._safe_timezone_name(user_timezone),
                    "user_timezone": self._safe_timezone_name(user_timezone),
                    "message": reminder_body,
                    "chat_id": self._resolve_reminder_chat_id(user_id, chat_id),
                    "status": "PENDING",
                    "retry_count": 0,
                    "last_error": "",
                    "notify_user_id": user_id,
                    "max_retries": 3,
                    "retry_delay_seconds": 30,
                },
                "Got it. I'll remind you every day.",
            )

        # once a week / weekly
        if "once a week" in lower or "every week" in lower or "weekly" in lower:
            weekday = now_local.weekday()
            task_name = f"weekly_{self._slug(reminder_body)}_{user_id}"
            return (
                {
                    "name": task_name,
                    "type": "reminder",
                    "interval": "weekly",
                    "enabled": True,
                    "at": f"{clock[0]:02d}:{clock[1]:02d}",
                    "timezone": self._safe_timezone_name(user_timezone),
                    "user_timezone": self._safe_timezone_name(user_timezone),
                    "weekdays": [weekday],
                    "message": reminder_body,
                    "chat_id": self._resolve_reminder_chat_id(user_id, chat_id),
                    "status": "PENDING",
                    "retry_count": 0,
                    "last_error": "",
                    "notify_user_id": user_id,
                    "max_retries": 3,
                    "retry_delay_seconds": 30,
                },
                "Got it. I'll remind you once a week.",
            )

        # in N minutes/hours/days
        in_match = _IN_INTERVAL_PATTERN.search(lower)
        if in_match and future_intent:
            value = int(in_match.group(1))
            unit = in_match.group(2)
            normalized = self._interval_unit_to_base(unit)
            delta = parse_relative_delta(value, unit)
            run_at = now_local + delta
            run_at_utc = run_at.astimezone(UTC)
            task_name = f"once_{self._slug(reminder_body)}_{int(now.timestamp())}_{user_id}"
            self._log_timezone_conversion(user_id, user_timezone, run_at.isoformat(), run_at_utc.isoformat())
            return (
                {
                    "name": task_name,
                    "type": "reminder",
                    "interval": "once",
                    "one_time": True,
                    "enabled": True,
                    "run_at": run_at_utc.isoformat(),
                    "timezone": self._safe_timezone_name(user_timezone),
                    "user_timezone": self._safe_timezone_name(user_timezone),
                    "message": reminder_body,
                    "chat_id": self._resolve_reminder_chat_id(user_id, chat_id),
                    "status": "PENDING",
                    "retry_count": 0,
                    "last_error": "",
                    "notify_user_id": user_id,
                    "max_retries": 3,
                    "retry_delay_seconds": 30,
                },
                f"Got it. I'll remind you in {value} {normalized}.",
            )

        # tomorrow at X
        if "tomorrow" in lower and future_intent:
            target_local = (now_local + timedelta(days=1)).replace(hour=clock[0], minute=clock[1], second=0, microsecond=0)
            target_utc = target_local.astimezone(UTC)
            task_name = f"tomorrow_{self._slug(reminder_body)}_{int(now.timestamp())}_{user_id}"
            self._log_timezone_conversion(user_id, user_timezone, target_local.isoformat(), target_utc.isoformat())
            return (
                {
                    "name": task_name,
                    "type": "reminder",
                    "interval": "once",
                    "one_time": True,
                    "enabled": True,
                    "run_at": target_utc.isoformat(),
                    "timezone": self._safe_timezone_name(user_timezone),
                    "user_timezone": self._safe_timezone_name(user_timezone),
                    "message": reminder_body,
                    "chat_id": self._resolve_reminder_chat_id(user_id, chat_id),
                    "status": "PENDING",
                    "retry_count": 0,
                    "last_error": "",
                    "notify_user_id": user_id,
                    "max_retries": 3,
                    "retry_delay_seconds": 30,
                },
                "Got it. I'll remind you tomorrow.",
            )

        # next Monday ...
        day_match = re.search(
            r"\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
            lower,
        )
        if day_match and future_intent:
            target_day = _WEEKDAY_TO_INDEX[day_match.group(1)]
            days_ahead = (target_day - now_local.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            target_local = (now_local + timedelta(days=days_ahead)).replace(
                hour=clock[0],
                minute=clock[1],
                second=0,
                microsecond=0,
            )
            target_utc = target_local.astimezone(UTC)
            task_name = f"next_{day_match.group(1)}_{self._slug(reminder_body)}_{int(now.timestamp())}_{user_id}"
            self._log_timezone_conversion(user_id, user_timezone, target_local.isoformat(), target_utc.isoformat())
            return (
                {
                    "name": task_name,
                    "type": "reminder",
                    "interval": "once",
                    "one_time": True,
                    "enabled": True,
                    "run_at": target_utc.isoformat(),
                    "timezone": self._safe_timezone_name(user_timezone),
                    "user_timezone": self._safe_timezone_name(user_timezone),
                    "message": reminder_body,
                    "chat_id": self._resolve_reminder_chat_id(user_id, chat_id),
                    "status": "PENDING",
                    "retry_count": 0,
                    "last_error": "",
                    "notify_user_id": user_id,
                    "max_retries": 3,
                    "retry_delay_seconds": 30,
                },
                f"Got it. I'll remind you next {day_match.group(1).capitalize()}.",
            )

        return None, None

    def _maybe_schedule_from_message(
        self,
        message: str,
        user_id: int,
        chat_id: int | None,
        user_timezone: str,
    ) -> str | None:
        if not self.scheduler:
            return None
        task, confirmation = self._parse_schedule_request(message, user_id, chat_id, user_timezone)
        if not task or not confirmation:
            return None

        existing_names = {str(t.get("name", "")) for t in self.scheduler.get_tasks()}
        if task["name"] in existing_names and task["name"].startswith("growth_checkin_"):
            return "I already have your growth check-in active and will keep it running."
        if task["name"] in existing_names:
            task["name"] = f"{task['name']}_{int(datetime.now(UTC).timestamp())}"

        self.scheduler.add_task(
            name=str(task["name"]),
            interval=str(task["interval"]),
            task_type=str(task.get("type", "reminder")),
            enabled=bool(task.get("enabled", True)),
            **{k: v for k, v in task.items() if k not in {"name", "interval", "type", "enabled"}},
        )
        ok, details = self.scheduler.persist_tasks()
        self._decision_logger.log(
            event_type="natural_schedule_created",
            summary=f"Created task '{task['name']}' from natural language",
            user_id=str(user_id),
            source="telegram",
            details={"task": task, "persisted": ok, "details": details},
        )
        if not ok:
            return f"{confirmation} I set it for now, but persistence is degraded ({details})."
        return confirmation

    @staticmethod
    def _is_safe_sandbox_command(command: str) -> bool:
        stripped = command.strip()
        if not stripped:
            return False
        if any(token in stripped for token in ("&&", "||", ";", "`", "$(")):
            return False
        allowed_prefixes = (
            "dig ",
            "ping ",
            "mtr ",
            "traceroute ",
            "nmap ",
            "openssl ",
            "curl ",
            "wget ",
            "python3 ",
            "node ",
            "bash ",
        )
        return stripped.startswith(allowed_prefixes)

    def _execute_interpreted_schedule_command(
        self,
        command: str,
        source_message: str,
        user_id: int,
        chat_id: int | None,
        user_timezone: str,
        confirmation: str,
    ) -> str:
        if not self.scheduler:
            return "Scheduler is currently unavailable."
        payload_text = command[len("SCHEDULE ") :].strip()
        task_payload = extract_json_object(payload_text)
        if not task_payload:
            return "I could not parse a valid schedule payload from the interpreter output."

        now_utc = datetime.now(UTC)
        try:
            task = self._normalize_ai_schedule_task(task_payload, user_id, chat_id, user_timezone, source_message, now_utc)
        except ValueError as exc:
            return str(exc)
        if not task:
            return "I could not normalize this schedule request into a valid task."

        existing_names = {str(t.get("name", "")) for t in self.scheduler.get_tasks()}
        if task["name"] in existing_names:
            task["name"] = f"{task['name']}_{int(now_utc.timestamp())}"

        self.scheduler.add_task(
            name=str(task["name"]),
            interval=str(task["interval"]),
            task_type=str(task.get("type", "reminder")),
            enabled=bool(task.get("enabled", True)),
            **{k: v for k, v in task.items() if k not in {"name", "interval", "type", "enabled"}},
        )
        ok, details = self.scheduler.persist_tasks()
        self._decision_logger.log(
            event_type="unified_interpreter_schedule",
            summary=f"Created task '{task['name']}'",
            user_id=str(user_id),
            source="telegram",
            details={"task": task, "persisted": ok, "details": details},
        )
        if ok:
            return confirmation
        return f"{confirmation} I set it for now, but persistence is degraded ({details})."

    def _execute_interpreted_sandbox_command(self, command: str, user_id: int) -> str:
        shell_command = command[len("SANDBOX ") :].strip()
        if not self._is_safe_sandbox_command(shell_command):
            return "I can only run single safe sandbox commands (no command chaining)."

        sandbox_ok, sandbox_reason = self._sandbox_capability()
        if not sandbox_ok:
            return (
                "Sandbox is currently unavailable, so I cannot run that command now.\n"
                f"Reason: {sandbox_reason}"
            )

        container_name = os.getenv("SANDBOX_CONTAINER_NAME", "her-sandbox")
        result = SandboxExecutor(container_name=container_name).execute_command(shell_command, timeout=75)
        self._decision_logger.log(
            event_type="unified_interpreter_sandbox",
            summary="Executed sandbox command",
            user_id=str(user_id),
            source="telegram",
            details={"command": shell_command, "exit_code": result.get("exit_code"), "success": result.get("success")},
        )
        lines = []
        lines.append("✅ Sandbox command executed." if result["success"] else "❌ Sandbox command failed.")
        if result["output"]:
            lines.append(f"Output:\n{result['output']}")
        if result["error"]:
            lines.append(f"Errors:\n{result['error']}")
        lines.append(f"Exit code: {result['exit_code']} | Time: {result['execution_time']:.2f}s")
        return "\n\n".join(lines)

    def _maybe_handle_unified_request(
        self,
        message: str,
        user_id: int,
        chat_id: int | None,
        user_timezone: str,
    ) -> str | None:
        if self._request_interpreter is None:
            return None
        timezone_name = os.getenv("TZ", "UTC")
        try:
            decision = self._request_interpreter.interpret(message=message, user_id=user_id, timezone_name=timezone_name)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Unified interpreter unavailable for user %s: %s", user_id, exc)
            return None

        if not decision or decision.intent == "none":
            return None

        self._decision_logger.log(
            event_type="unified_interpreter_decision",
            summary=f"Interpreter intent={decision.intent}",
            user_id=str(user_id),
            source="telegram",
            details={
                "language": decision.language,
                "english": decision.english,
                "command": decision.command,
            },
        )
        if decision.intent == "schedule":
            return self._execute_interpreted_schedule_command(
                command=decision.command,
                source_message=message,
                user_id=user_id,
                chat_id=chat_id,
                user_timezone=user_timezone,
                confirmation=decision.confirmation,
            )
        if decision.intent == "sandbox":
            return self._execute_interpreted_sandbox_command(decision.command, user_id=user_id)
        return None


    def _build_live_context(self, message: str) -> str:
        now_utc = datetime.now(UTC)
        snippets = [f"Current UTC timestamp: {now_utc.isoformat()}"]
        lower_msg = message.lower()
        caps = self._get_runtime_capabilities()
        internet = (caps.get("capabilities", {}) or {}).get("internet", {}) if caps else {}
        if internet:
            snippets.append(
                "Runtime internet capability: "
                f"available={bool(internet.get('available'))}, reason={internet.get('reason', 'unknown')}"
            )

        if any(token in lower_msg for token in {"bitcoin", "btc"}):
            usd_price = self._fetch_btc_price_usd()
            if usd_price is not None:
                snippets.append(f"Live market data: Bitcoin (BTC) price is about ${usd_price:,.2f} USD.")

        live_web_enabled = os.getenv("HER_ENABLE_LIVE_WEB_CONTEXT", "false").strip().lower() in {"1", "true", "yes", "on"}
        needs_web_search = any(
            token in lower_msg
            for token in {"today", "current", "latest", "right now", "price", "news", "internet", "search"}
        )
        internet_available = bool((internet or {}).get("available", True))
        if live_web_enabled and needs_web_search and internet_available:
            search_result = self._web_search_tool._run(message, max_results=3)
            if not search_result.lower().startswith("web search failed"):
                snippets.append(f"Fresh web context:\n{search_result}")
            else:
                snippets.append(f"Web search attempt failed at runtime: {search_result}")

        return "\n".join(snippets)

    def _get_runtime_capabilities(self) -> dict[str, Any]:
        if not self._metrics:
            return {}
        try:
            raw = self._metrics._client.get("her:runtime:capabilities")  # noqa: SLF001
            if not raw:
                return {}
            payload = json.loads(raw)
            return payload if isinstance(payload, dict) else {}
        except Exception as exc:  # noqa: BLE001
            logger.debug("Runtime capability lookup skipped: %s", exc)
            return {}

    def _build_reply_prompt(
        self,
        user_id: str,
        message: str,
        language: str,
        user_context: list[dict[str, Any]],
        group_context: list[dict[str, Any]],
        memories: list[dict[str, Any]],
        live_context: str,
    ) -> str:
        recent_user = "\n".join(
            f"- {item.get('role', 'user')}: {item.get('message', '')}" for item in user_context[-8:]
        ) or "(none)"
        recent_group = "\n".join(
            f"- {item.get('role', 'user')}: {item.get('message', '')}" for item in group_context[-8:]
        ) or "(none)"
        related_memory_text = "\n".join(
            f"- {m.get('memory') or m.get('text') or m.get('data') or m}" for m in memories[:5]
        ) or "(none)"
        style_summary = self._reinforcement.style_guidance(user_id)
        profile = self._user_profiles.get_personalization_profile(user_id)
        display_name = profile.nickname or profile.name or ""

        return (
            "You are HER, a warm emotionally intelligent assistant in Telegram. "
            "Answer naturally and concisely.\n\n"
            "Production-safe response policy:\n"
            "- Be predictable, calm, and non-repetitive.\n"
            "- Never send unsolicited follow-up messages or reminders.\n"
            "- If the user stops replying, remain silent.\n"
            "- Always answer the user's message directly before asking anything.\n"
            "- Ask at most one clarification question and only when required.\n"
            "- Do not ask onboarding/profile questions unless user explicitly asks for setup/config/reset.\n"
            "- Do not fabricate prior context.\n"
            "- If user criticizes the response, apologize briefly once, then adjust.\n"
            "- Keep language consistent with the user's dominant language.\n\n"
            "Execution posture for actionable requests:\n"
            "- Treat each user request as an objective to complete.\n"
            "- Build a short step-by-step plan before suggesting execution.\n"
            "- Prefer exact commands or code over vague advice.\n"
            "- If a step fails, diagnose, adapt, and retry with an alternative.\n"
            "- Do not default to refusal language; provide the best feasible next action.\n"
            "- Infer likely user intent when details are missing, then proceed pragmatically.\n"
            "- Keep outputs practical and operator-like.\n\n"
            "Runtime capabilities available to HER may include bash terminal, internet, file system, "
            "installed packages, package installation, background processes, network tools, and persistent workspace. "
            "Use live context below to stay truthful about what is currently available.\n\n"
            f"Respond strictly in language code: {language}. Do not switch language.\n"
            f"User preferred name: {display_name or '(unknown)'}\n"
            f"User timezone: {profile.timezone}\n"
            f"Conversation style preference: {profile.conversation_style}\n\n"
            f"Adaptive communication profile: {style_summary}\n\n"
            f"Recent user context:\n{recent_user}\n\n"
            f"Recent group context:\n{recent_group}\n\n"
            f"Relevant long-term memories:\n{related_memory_text}\n\n"
            f"Real-time context:\n{live_context}\n\n"
            f"Current user message: {message}"
        )

    @staticmethod
    def _user_requested_profile_setup(message: str) -> bool:
        return bool(_PROFILE_SETUP_PATTERN.search(str(message or "")))

    @staticmethod
    def _contains_disallowed_onboarding_questions(text: str) -> bool:
        return bool(_ONBOARDING_QUESTION_PATTERN.search(str(text or "")))

    def _fallback_guardrail_reply(self, language: str) -> str:
        if language == "fa":
            return "بدون تنظیمات اولیه هم ادامه می‌دهم. درخواستت را مستقیم می‌گیرم و پاسخ می‌دهم."
        return "I can continue without setup details and respond directly to your request."

    def _sanitize_response_for_policy(
        self,
        *,
        response: str,
        user_message: str,
        user_language: str,
        previous_assistant_message: str,
    ) -> str:
        cleaned = str(response or "").strip()
        if not cleaned:
            return self._fallback_guardrail_reply(user_language)

        setup_requested = self._user_requested_profile_setup(user_message)
        if not setup_requested and self._contains_disallowed_onboarding_questions(cleaned):
            return self._fallback_guardrail_reply(user_language)

        if previous_assistant_message and cleaned.strip() == previous_assistant_message.strip():
            if user_language == "fa":
                return "پاسخ قبلی را تکرار نمی‌کنم. دقیق بگو کدام بخش را می‌خواهی جلو ببریم."
            return "I won't repeat the same prompt. Tell me the exact part you want to continue."

        if _CRITICISM_PATTERN.search(str(user_message or "")):
            if user_language == "fa":
                return "حق با توئه. اشتباه شد. بگو دقیقاً چی می‌خوای تا درستش کنم."
            return "You are right. That was a miss. Tell me exactly what you want and I'll correct it."

        return cleaned

    def _last_assistant_message(self, context_rows: list[dict[str, Any]]) -> str:
        for item in reversed(context_rows):
            if str(item.get("role", "")).lower() == "assistant":
                return str(item.get("message", ""))
        return ""

    def _record_reinforcement(
        self,
        user_id: str,
        user_message: str,
        assistant_message: str,
        task_succeeded: bool,
    ) -> None:
        if not assistant_message.strip():
            return
        outcome = self._reinforcement.evaluate(
            user_id=user_id,
            user_message=user_message,
            assistant_message=assistant_message,
            task_succeeded=task_succeeded,
        )
        lesson = (
            "Reinforcement lesson: "
            f"score={outcome.score}, label={outcome.label}, reasoning={','.join(outcome.reasoning[:6])}"
        )
        try:
            self.memory.add_memory(user_id, lesson, "reinforcement_lesson", 0.7)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to persist reinforcement lesson memory: %s", exc)

    @staticmethod
    def _maybe_recurring_suggestion(message: str) -> str | None:
        lower = message.lower()
        if any(token in lower for token in {"i forgot again", "keep forgetting", "again forgot", "hard to remember"}):
            return "If you want, I can set this as a recurring reminder automatically."
        if any(token in lower for token in {"goal", "habit", "routine"}) and "every" not in lower:
            return "I can also turn this into a recurring check-in so we track progress over time."
        return None

    @staticmethod
    def _extract_retry_after_seconds(message: str) -> int | None:
        match = _RETRY_IN_MIN_SEC_PATTERN.search(message)
        if match:
            minutes = int(match.group(1))
            seconds = float(match.group(2))
            return max(1, int(minutes * 60 + seconds))
        match = _RETRY_AFTER_SECONDS_PATTERN.search(message)
        if match:
            return max(1, int(match.group(1)))
        return None

    @staticmethod
    def _extract_http_status_code(exc: BaseException) -> int | None:
        status_code = getattr(exc, "status_code", None)
        if isinstance(status_code, int):
            return status_code
        response = getattr(exc, "response", None)
        response_status = getattr(response, "status_code", None) if response is not None else None
        if isinstance(response_status, int):
            return response_status
        match = re.search(r"\berror code:\s*(\d{3})\b", str(exc), re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None

    def _build_transient_llm_error_reply(self, exc: BaseException) -> str:
        message = str(exc)
        status_code = self._extract_http_status_code(exc)
        retry_after = self._extract_retry_after_seconds(message)
        if status_code == 429:
            if retry_after is not None:
                return (
                    "I'm temporarily rate-limited by the model provider. "
                    f"Please retry in about {retry_after} seconds."
                )
            return "I'm temporarily rate-limited by the model provider. Please retry in a bit."
        if status_code in {502, 503, 504}:
            return (
                "I'm having temporary trouble reaching the model provider right now. "
                "Please retry in a moment."
            )
        return "I am here with you. I hit a temporary issue generating a full reply."

    def _invoke_llm_with_fallback(self, messages: list[Any], user_id: int) -> tuple[str, bool]:
        response_obj = self._llm.invoke(messages)
        response_text = (response_obj.content or "").strip() if response_obj else ""
        if response_text:
            return response_text, False

        primary_error = ValueError("Primary LLM returned an empty response.")
        if self._fallback_llm:
            try:
                fallback_obj = self._fallback_llm.invoke(messages)
                fallback_text = (fallback_obj.content or "").strip() if fallback_obj else ""
                if fallback_text:
                    logger.warning(
                        "Primary LLM provider '%s' returned empty output; using fallback '%s' for user %s.",
                        self._llm_provider,
                        self._fallback_provider,
                        user_id,
                    )
                    return fallback_text, True
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Fallback provider '%s' failed after empty output from primary '%s' for user %s: %s",
                    self._fallback_provider,
                    self._llm_provider,
                    user_id,
                    exc,
                )
        raise primary_error

    def _generate_response_with_failover(self, messages: list[Any], user_id: int) -> tuple[str, bool]:
        try:
            return self._invoke_llm_with_fallback(messages, user_id)
        except Exception as primary_exc:  # noqa: BLE001
            status_code = self._extract_http_status_code(primary_exc)
            if status_code in {502, 503} and self._fallback_llm:
                logger.warning(
                    "Primary LLM provider '%s' failed with status %s; retrying with fallback '%s' for user %s.",
                    self._llm_provider,
                    status_code,
                    self._fallback_provider,
                    user_id,
                )
                try:
                    fallback_obj = self._fallback_llm.invoke(messages)
                    fallback_text = (fallback_obj.content or "").strip() if fallback_obj else ""
                    if fallback_text:
                        self._decision_logger.log(
                            event_type="llm_failover",
                            summary="Primary LLM provider failed; fallback provider served response",
                            user_id=str(user_id),
                            source="telegram",
                            details={
                                "primary_provider": self._llm_provider,
                                "fallback_provider": self._fallback_provider,
                                "status_code": status_code,
                            },
                        )
                        return fallback_text, True
                    raise ValueError("Fallback LLM returned an empty response.")
                except Exception as fallback_exc:  # noqa: BLE001
                    logger.exception(
                        "Fallback LLM provider '%s' also failed for user %s after primary status %s: %s",
                        self._fallback_provider,
                        user_id,
                        status_code,
                        fallback_exc,
                    )
            raise primary_exc

    def _log_stage_timing(self, user_id: int, stage: str, started_at: float, extra: dict[str, Any] | None = None) -> None:
        duration_ms = round((time.perf_counter() - started_at) * 1000.0, 2)
        payload: dict[str, Any] = {"stage": stage, "duration_ms": duration_ms}
        if extra:
            payload.update(extra)
        self._decision_logger.log(
            event_type="performance_timing",
            summary=f"{stage} {duration_ms}ms",
            user_id=str(user_id),
            source="telegram",
            details=payload,
        )

    @staticmethod
    def _classify_intent(message: str) -> dict[str, Any]:
        text = message.strip()
        lower = text.lower()
        is_greeting = bool(_GREETING_PATTERN.match(text))
        has_action_word = bool(_ACTION_WORD_PATTERN.search(text))
        has_schedule_word = bool(_SCHEDULE_WORD_PATTERN.search(text))
        has_command_shape = lower.startswith(("run ", "execute ", "test ", "check ", "scan ", "trace "))
        has_tool_word = any(token in lower for token in ("mtr", "traceroute", "dig", "ping", "nmap", "curl", "wget"))
        action_confidence = 0.95 if (has_action_word and (has_command_shape or has_tool_word)) else 0.1
        if is_greeting and not has_tool_word:
            action_confidence = 0.0
        mode = ACTION_MODE if action_confidence >= ACTION_INTENT_THRESHOLD else CHAT_MODE
        return {
            "mode": mode,
            "is_greeting": is_greeting,
            "action_confidence": action_confidence,
            "has_schedule_word": has_schedule_word,
        }

    @staticmethod
    def _requires_tool_execution(message: str) -> bool:
        lower = str(message or "").lower()
        required_tokens = {
            "math",
            "time",
            "search",
            "fetch",
            "compute",
            "system",
            "file",
            "data",
            "run",
            "execute",
            "check",
            "scan",
            "price",
            "latest",
            "today",
        }
        return any(token in lower for token in required_tokens)

    def _capture_profile_from_message(self, user_id: int, message: str, language: str) -> None:
        text = str(message or "").strip()
        if not text:
            return
        lowered = text.lower()
        name = None
        nickname = None
        timezone_name = None
        style = None

        name_match = re.search(r"(?:my name is|name[:\\s]+)([a-zA-Z\\s]{2,40})", text, re.IGNORECASE)
        if name_match:
            name = name_match.group(1).strip()
        nick_match = re.search(r"(?:call me|nickname[:\\s]+)([a-zA-Z\\s]{2,40})", text, re.IGNORECASE)
        if nick_match:
            nickname = nick_match.group(1).strip()
        tz_match = re.search(r"([A-Za-z]+/[A-Za-z_]+)", text)
        if tz_match:
            timezone_name = tz_match.group(1).strip()
        if any(token in lowered for token in {"concise", "brief", "short"}):
            style = "concise"
        elif any(token in lowered for token in {"analytical", "detailed", "deep"}):
            style = "analytical"
        elif any(token in lowered for token in {"friendly", "warm", "supportive"}):
            style = "friendly"

        self._user_profiles.upsert_personalization_profile(
            user_id=user_id,
            name=name,
            nickname=nickname,
            timezone_name=timezone_name,
            preferred_language=language,
            conversation_style=style,
        )
        if any(value is not None for value in {name, nickname, timezone_name, style}):
            memory_line = (
                f"profile_update name={name or ''} "
                f"nickname={nickname or ''} timezone={timezone_name or ''} style={style or ''}"
            )
            try:
                self.memory.add_memory(str(user_id), memory_line, "profile_identity", 0.95)
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    def _extract_immediate_shell_command(message: str) -> str | None:
        lower = message.strip().lower()
        host_match = _HOST_PATTERN.search(lower)
        host = host_match.group(1) if host_match else ""
        if "mtr" in lower and host:
            return f"mtr --report --report-cycles 10 {host}"
        if "traceroute" in lower and host:
            return f"traceroute -m 15 {host}"
        if "dns" in lower and host:
            return f"dig +short {host}"
        if "ping" in lower and host:
            return f"ping -c 4 {host}"
        run_match = re.match(r"^\s*(?:please\s+)?(?:run|execute)\s+(.+)$", message.strip(), re.IGNORECASE)
        if run_match:
            raw = run_match.group(1).strip()
            return raw if raw else None
        for prefix in ("mtr ", "dig ", "ping ", "traceroute ", "nmap ", "curl ", "wget "):
            if lower.startswith(prefix):
                return message.strip()
        return None

    @staticmethod
    def _explicitly_requests_scheduling(message: str) -> bool:
        return bool(_SCHEDULE_WORD_PATTERN.search(message))

    async def _stream_sandbox_command(
        self,
        update: Update,
        user_id: int,
        command: str,
        execution_id: str | None = None,
    ) -> tuple[str, bool]:
        self._emit_workflow_event(
            execution_id=execution_id,
            event_type="tool_execution_started",
            node_id="tool_executor",
            status="running",
            details={"command": command},
        )
        progress = await update.effective_message.reply_text(f"▶️ Executing now in sandbox:\n{command}")
        buffer_lines: list[str] = []
        lock = asyncio.Lock()
        last_edit = 0.0

        async def _render_partial(force: bool = False) -> None:
            nonlocal last_edit
            now = time.monotonic()
            if not force and now - last_edit < 0.8:
                return
            if not buffer_lines:
                return
            text = "\n".join(buffer_lines[-20:])[-3200:]
            try:
                async with lock:
                    await progress.edit_text(f"▶️ Running...\n\n{text}")
                last_edit = now
            except Exception:  # noqa: BLE001
                pass

        async def _on_stdout(line: str) -> None:
            if line.strip():
                buffer_lines.append(line)
                self._emit_workflow_event(
                    execution_id=execution_id,
                    event_type="tool_stdout",
                    node_id="tool_executor",
                    status="running",
                    details={"line": line, "stream": "stdout"},
                )
                await _render_partial()

        async def _on_stderr(line: str) -> None:
            if line.strip():
                buffer_lines.append(f"[stderr] {line}")
                self._emit_workflow_event(
                    execution_id=execution_id,
                    event_type="tool_stdout",
                    node_id="tool_executor",
                    status="running",
                    details={"line": line, "stream": "stderr"},
                )
                await _render_partial()

        tool_start = time.perf_counter()
        container_name = os.getenv("SANDBOX_CONTAINER_NAME", "her-sandbox")
        result = await SandboxExecutor(container_name=container_name).execute_command_stream(
            command=command,
            timeout=int(os.getenv("HER_SANDBOX_COMMAND_TIMEOUT_SECONDS", "30")),
            on_stdout_line=_on_stdout,
            on_stderr_line=_on_stderr,
        )
        self._log_stage_timing(user_id, "tool_execution", tool_start, {"command": command, "exit_code": result.get("exit_code")})
        self._emit_workflow_event(
            execution_id=execution_id,
            event_type="tool_completed",
            node_id="tool_executor",
            status="success" if result.get("success") else "error",
            details={
                "command": command,
                "exit_code": result.get("exit_code"),
                "duration_ms": round(float(result.get("execution_time", 0.0)) * 1000.0, 2),
                "tool_output": str(result.get("output", ""))[-5000:],
                "tool_error": str(result.get("error", ""))[-2000:],
            },
        )
        await _render_partial(force=True)

        lines = ["✅ Command executed." if result["success"] else f"❌ Command failed (exit={result['exit_code']})."]
        if result.get("output"):
            lines.append(f"Output:\n{result['output']}")
        if result.get("error"):
            lines.append(f"Errors:\n{result['error']}")
        lines.append(f"Time: {result.get('execution_time', 0):.2f}s")
        final = "\n\n".join(lines)[:3900]
        try:
            await progress.edit_text(final)
        except Exception:  # noqa: BLE001
            await self._reply(update, final)
        return final, bool(result["success"])

    async def _stream_chat_response(
        self,
        update: Update,
        user_id: int,
        messages: list[Any],
        user_message: str,
        user_language: str,
        previous_assistant_message: str,
        execution_id: str | None = None,
    ) -> str:
        self._emit_workflow_event(
            execution_id=execution_id,
            event_type="llm_started",
            node_id="llm",
            status="running",
            details={
                "provider": self._llm_provider,
                "raw_messages": [str(getattr(msg, "content", "")) for msg in messages],
            },
        )
        progress = await update.effective_message.reply_text("…")
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()
        llm_error: list[BaseException] = []
        used_fallback = False

        def _produce() -> None:
            try:
                for chunk in self._llm.stream(messages):
                    token = getattr(chunk, "content", "")
                    if isinstance(token, list):
                        token = "".join(str(x) for x in token)
                    token_text = str(token)
                    if token_text:
                        asyncio.run_coroutine_threadsafe(queue.put(token_text), loop)
            except Exception as exc:  # noqa: BLE001
                llm_error.append(exc)
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(None), loop)

        llm_start = time.perf_counter()
        worker = threading.Thread(target=_produce, daemon=True)
        worker.start()

        assembled = ""
        last_edit = 0.0
        while True:
            token = await queue.get()
            if token is None:
                break
            assembled += token
            self._emit_workflow_event(
                execution_id=execution_id,
                event_type="llm_stream_token",
                node_id="llm",
                status="running",
                details={"token": token},
            )
            now = time.monotonic()
            if now - last_edit >= 0.6 and assembled.strip():
                try:
                    await progress.edit_text(assembled[:3900])
                    last_edit = now
                except Exception:  # noqa: BLE001
                    pass

        if llm_error or not assembled.strip():
            reply, used_fallback = self._generate_response_with_failover(messages, user_id)
            assembled = reply

        self._log_stage_timing(user_id, "llm", llm_start, {"used_fallback": used_fallback})
        self._emit_workflow_event(
            execution_id=execution_id,
            event_type="llm_completed",
            node_id="llm",
            status="success" if assembled.strip() else "error",
            details={
                "used_fallback": used_fallback,
                "duration_ms": round((time.perf_counter() - llm_start) * 1000.0, 2),
            },
        )
        final_text = assembled.strip() or "I am here with you."
        final_text = self._sanitize_response_for_policy(
            response=final_text,
            user_message=user_message,
            user_language=user_language,
            previous_assistant_message=previous_assistant_message,
        )
        try:
            await progress.edit_text(final_text[:3900])
        except Exception:  # noqa: BLE001
            await self._reply(update, final_text[:3900])
        return final_text

    async def _execute_agent(
        self,
        *,
        user_id: int,
        message: str,
        user_language: str,
        previous_context: list[dict[str, Any]],
        execution_id: str | None,
    ) -> tuple[str, bool]:
        sandbox_ok, sandbox_reason = self._sandbox_capability()
        if not sandbox_ok:
            return (
                self._render_in_user_language(
                    user_id,
                    user_language,
                    f"Sandbox is unavailable. Unsafe/direct execution is blocked. Reason: {sandbox_reason}",
                ),
                False,
            )

        debate = self._run_internal_debate(
            user_id=user_id,
            message=message,
            user_language=user_language,
            previous_context=previous_context,
        )
        self._emit_workflow_event(
            execution_id=execution_id,
            event_type="debate",
            node_id="tool_selector",
            status="success",
            details={
                "event": "debate",
                "planner": debate.get("planner", {}),
                "skeptic": debate.get("skeptic", {}),
                "decision": "approved" if debate.get("approved", False) else "rejected",
            },
        )
        self._decision_logger.log(
            event_type="internal_debate",
            summary=f"Planner/Skeptic decision for user {user_id}",
            user_id=str(user_id),
            source="telegram",
            details=debate,
        )
        if not bool(debate.get("approved", False)):
            fallback = str(
                debate.get("skeptic", {}).get("notes")
                or "I need a clearer, verifiable action request before running tools."
            )
            return self._render_in_user_language(user_id, user_language, fallback)[:3900], False

        self._emit_workflow_event(
            execution_id=execution_id,
            event_type="step_start",
            node_id="tool_selector",
            status="running",
            details={"step_number": 1, "action": "plan"},
        )
        self._emit_workflow_event(
            execution_id=execution_id,
            event_type="step_complete",
            node_id="tool_selector",
            status="success",
            details={"step_number": 1, "action": "plan", "verified": True, "output_preview": "plan_ready"},
        )

        def _on_step_event(payload: dict[str, Any]) -> None:
            event = str(payload.get("event", ""))
            self._emit_workflow_event(
                execution_id=execution_id,
                event_type=event,
                node_id="tool_executor",
                status="running" if event == "step_start" else "success",
                details=payload,
            )

        result = self._autonomous_operator.execute_with_history(
            user_request=message,
            user_id=user_id,
            conversation_history=previous_context[-50:],
            language=user_language,
            on_step_event=_on_step_event,
        )
        final_text = str(result.get("result", "")).strip() or "Completed."
        verifier = self._verifier_review(
            user_id=user_id,
            message=message,
            user_language=user_language,
            operator_result=final_text,
        )
        self._decision_logger.log(
            event_type="verifier_result",
            summary=f"Verifier completed for user {user_id}",
            user_id=str(user_id),
            source="telegram",
            details=verifier,
        )
        self._emit_workflow_event(
            execution_id=execution_id,
            event_type="debate",
            node_id="tool_executor",
            status="success" if bool(verifier.get("verified", False)) else "error",
            details={
                "event": "debate",
                "verifier": verifier,
                "decision": "approved" if bool(verifier.get("verified", False)) else "rejected",
            },
        )
        if not bool(verifier.get("verified", False)):
            final_text = str(verifier.get("notes") or "Execution result could not be verified safely.")
        response = self._render_in_user_language(user_id, user_language, final_text)
        return response[:3900], bool(verifier.get("verified", False))

    def _run_internal_debate(
        self,
        *,
        user_id: int,
        message: str,
        user_language: str,
        previous_context: list[dict[str, Any]],
    ) -> dict[str, Any]:
        planner = self._planner_proposal(user_id=user_id, message=message, user_language=user_language, previous_context=previous_context)
        skeptic = self._skeptic_review(
            user_id=user_id,
            user_language=user_language,
            message=message,
            planner=planner,
        )
        approved = bool(skeptic.get("approved", False)) and bool(planner.get("tool_required", True))
        return {"planner": planner, "skeptic": skeptic, "approved": approved}

    def _planner_proposal(
        self,
        *,
        user_id: int,
        message: str,
        user_language: str,
        previous_context: list[dict[str, Any]],
    ) -> dict[str, Any]:
        context_preview = "\n".join(
            f"{str(row.get('role', 'user'))}: {str(row.get('message', ''))[:140]}" for row in previous_context[-8:]
        )
        prompt = (
            "You are Planner.\n"
            "Return strict JSON only with keys: tool_required (bool), action (string), assumptions (array), risk (low|medium|high).\n"
            f"Language: {user_language}\n"
            f"User message: {message}\n"
            f"Recent context:\n{context_preview or '(none)'}"
        )
        try:
            raw, _ = self._generate_response_with_failover(
                [SystemMessage(content="Planner role for safe tool planning. JSON only."), HumanMessage(content=prompt)],
                user_id,
            )
            parsed = extract_json_object(raw)
            if isinstance(parsed, dict):
                return {
                    "tool_required": bool(parsed.get("tool_required", True)),
                    "action": str(parsed.get("action", "sandbox_execute")),
                    "assumptions": list(parsed.get("assumptions", [])) if isinstance(parsed.get("assumptions"), list) else [],
                    "risk": str(parsed.get("risk", "medium")),
                }
        except Exception:  # noqa: BLE001
            pass
        return {
            "tool_required": True,
            "action": "sandbox_execute",
            "assumptions": ["User intent is explicit action request."],
            "risk": "medium",
        }

    def _skeptic_review(
        self,
        *,
        user_id: int,
        user_language: str,
        message: str,
        planner: dict[str, Any],
    ) -> dict[str, Any]:
        prompt = (
            "You are Skeptic.\n"
            "Evaluate planner proposal for safety and hallucination risk.\n"
            "Return strict JSON with keys: approved (bool), tool_needed (bool), assumption_safe (bool), "
            "hallucination_risk (low|medium|high), notes (string).\n"
            f"Language: {user_language}\n"
            f"User message: {message}\n"
            f"Planner JSON: {json.dumps(planner, ensure_ascii=True)}"
        )
        try:
            raw, _ = self._generate_response_with_failover(
                [SystemMessage(content="Skeptic role for execution gating. JSON only."), HumanMessage(content=prompt)],
                user_id,
            )
            parsed = extract_json_object(raw)
            if isinstance(parsed, dict):
                risk = str(parsed.get("hallucination_risk", "medium")).strip().lower()
                approved = bool(parsed.get("approved", False)) and risk in {"low", "medium"}
                if not bool(planner.get("tool_required", True)):
                    approved = False
                return {
                    "approved": approved,
                    "tool_needed": bool(parsed.get("tool_needed", True)),
                    "assumption_safe": bool(parsed.get("assumption_safe", False)),
                    "hallucination_risk": risk,
                    "notes": str(parsed.get("notes", "")),
                }
        except Exception:  # noqa: BLE001
            pass

        obvious_risky = bool(_GREETING_PATTERN.match(message)) or len(message.strip()) < 6
        return {
            "approved": not obvious_risky,
            "tool_needed": True,
            "assumption_safe": not obvious_risky,
            "hallucination_risk": "high" if obvious_risky else "medium",
            "notes": "Rejected because request is too vague for safe execution." if obvious_risky else "Approved with bounded sandbox execution.",
        }

    def _verifier_review(
        self,
        *,
        user_id: int,
        message: str,
        user_language: str,
        operator_result: str,
    ) -> dict[str, Any]:
        prompt = (
            "You are Verifier.\n"
            "Return strict JSON: verified (bool), confidence (0..1), notes (string).\n"
            f"Language: {user_language}\n"
            f"User request: {message}\n"
            f"Execution result: {operator_result[:1500]}"
        )
        try:
            raw, _ = self._generate_response_with_failover(
                [SystemMessage(content="Verifier role for post-execution validation. JSON only."), HumanMessage(content=prompt)],
                user_id,
            )
            parsed = extract_json_object(raw)
            if isinstance(parsed, dict):
                confidence = float(parsed.get("confidence", 0.0) or 0.0)
                verified = bool(parsed.get("verified", False)) and confidence >= 0.45
                return {
                    "verified": verified,
                    "confidence": round(confidence, 3),
                    "notes": str(parsed.get("notes", "")),
                }
        except Exception:  # noqa: BLE001
            pass
        fallback_verified = bool(operator_result.strip())
        return {
            "verified": fallback_verified,
            "confidence": 0.5 if fallback_verified else 0.1,
            "notes": "Verified by fallback non-empty output check." if fallback_verified else "Execution returned empty result.",
        }

    async def process_message_api(
        self,
        user_id: int,
        message: str,
        chat_id: int | None = None,
        debug: bool = False,
    ) -> dict[str, Any]:
        message = str(message or "").strip()
        if not message:
            raise ValueError("Message cannot be empty")

        chat_id = chat_id if chat_id is not None else user_id
        user_timezone = self._persist_user_runtime_profile(user_id=user_id, chat_id=chat_id)
        execution_id = (
            self._workflow_event_hub.create_execution(user_id=str(user_id), message=message)
            if self._workflow_event_hub
            else None
        )
        request_started_at = time.perf_counter()
        self._emit_workflow_event(
            execution_id=execution_id,
            event_type="message_received",
            node_id="input",
            status="success",
            details={"message": message, "source": "api"},
        )

        memory_start = time.perf_counter()
        self._emit_workflow_event(
            execution_id=execution_id,
            event_type="tool_execution_started",
            node_id="memory_lookup",
            status="running",
            details={"phase": "initial_context"},
        )
        previous_context = self.memory.get_context(str(user_id))
        previous_assistant_message = self._last_assistant_message(previous_context)
        self._log_stage_timing(user_id, "memory_lookup", memory_start, {"context_size": len(previous_context)})
        self._emit_workflow_event(
            execution_id=execution_id,
            event_type="tool_completed",
            node_id="memory_lookup",
            status="success",
            details={
                "phase": "initial_context",
                "duration_ms": round((time.perf_counter() - memory_start) * 1000.0, 2),
                "context_size": len(previous_context),
            },
        )

        user_language = self._detect_user_language(message, user_id, previous_context)
        self._capture_profile_from_message(user_id, message, user_language)
        self._user_profiles.upsert_personalization_profile(user_id=user_id, preferred_language=user_language)
        autonomy_before = self._autonomy.get_profile(str(user_id))
        response_seconds = None
        if autonomy_before.last_proactive_at is not None:
            response_seconds = (datetime.now(UTC) - autonomy_before.last_proactive_at).total_seconds()
        autonomy_signals = self._autonomy.record_user_message(
            user_id=str(user_id),
            message=message,
            user_initiated=response_seconds is None or response_seconds >= 6 * 3600,
            response_seconds=response_seconds,
        )
        if bool(autonomy_signals.get("disabled")):
            self._user_profiles.upsert_personalization_profile(user_id=user_id, proactive_opt_out=True)
        elif "/unmute" in message.lower() or "enable proactive" in message.lower():
            self._user_profiles.upsert_personalization_profile(user_id=user_id, proactive_opt_out=False)

        if not self.is_admin(user_id) and not self.rate_limiter.is_allowed(user_id):
            response = self._render_in_user_language(user_id, user_language, "⏱️ Please slow down a bit!")
            return {
                "execution_id": execution_id or "",
                "response": response,
                "mode": CHAT_MODE,
                "language": user_language,
                "scheduled_tasks": 0,
                "task_succeeded": False,
                "total_latency_ms": round((time.perf_counter() - request_started_at) * 1000.0, 2),
            }

        self.memory.update_context(str(user_id), message, "user")
        intent = self._classify_intent(message)
        if self._requires_tool_execution(message):
            intent["mode"] = ACTION_MODE
            intent["action_confidence"] = 1.0
        self._emit_workflow_event(
            execution_id=execution_id,
            event_type="intent_detected",
            node_id="intent_classifier",
            status="success",
            details={
                "mode": intent["mode"],
                "action_confidence": intent["action_confidence"],
                "has_schedule_word": intent["has_schedule_word"],
            },
        )

        response = ""
        task_succeeded = True
        schedule_count = 0

        try:
            if intent["mode"] == ACTION_MODE:
                explicit_schedule = self._explicitly_requests_scheduling(message)
                if explicit_schedule and self.scheduler:
                    self._emit_workflow_event(
                        execution_id=execution_id,
                        event_type="tool_selected",
                        node_id="tool_selector",
                        status="success",
                        details={"selected": "scheduler"},
                    )
                    scheduler_start = time.perf_counter()
                    all_scheduled_tasks, _ = self._parse_multi_intent_schedule_with_llm(
                        message=message,
                        user_id=user_id,
                        chat_id=chat_id,
                        user_timezone=user_timezone,
                        language=user_language,
                        context_rows=previous_context,
                    )
                    response_parts: list[str] = []
                    created_task_count = 0
                    ok = True
                    details = "no tasks created"
                    if all_scheduled_tasks:
                        created_task_count = len(all_scheduled_tasks)
                        existing_names = {str(t.get("name", "")) for t in self.scheduler.get_tasks()}
                        for task in all_scheduled_tasks:
                            task_name = str(task.get("name", "task"))
                            if task_name in existing_names:
                                task_name = f"{task_name}_{int(datetime.now(UTC).timestamp())}"
                                task["name"] = task_name
                            existing_names.add(task_name)
                            self.scheduler.add_task(
                                name=task_name,
                                interval=str(task.get("interval", "once")),
                                task_type=str(task.get("type", "reminder")),
                                enabled=bool(task.get("enabled", True)),
                                **{k: v for k, v in task.items() if k not in {"name", "interval", "type", "enabled"}},
                            )
                            response_parts.append(
                                self._build_scheduler_confirmation(
                                    user_id=user_id,
                                    language=user_language,
                                    original_request=message,
                                    task=task,
                                    context_rows=previous_context,
                                )
                            )
                        ok, details = self.scheduler.persist_tasks()
                    else:
                        fallback_confirmation = self._maybe_schedule_from_message(
                            message=message,
                            user_id=user_id,
                            chat_id=chat_id,
                            user_timezone=user_timezone,
                        )
                        if fallback_confirmation:
                            response_parts.append(fallback_confirmation)
                            created_task_count = 1
                            ok, details = True, "created via deterministic fallback parser"
                        else:
                            ok, details = False, "could not infer a valid schedule task from request"
                    self._log_stage_timing(
                        user_id,
                        "scheduler",
                        scheduler_start,
                        {"created_tasks": created_task_count, "persisted": ok},
                    )
                    if not ok:
                        response_parts.append(f"Scheduler persistence is degraded: {details}")
                    response = "\n".join(part for part in response_parts if part).strip()
                    schedule_count = created_task_count
                    task_succeeded = ok and created_task_count > 0
                else:
                    self._emit_workflow_event(
                        execution_id=execution_id,
                        event_type="tool_selected",
                        node_id="tool_selector",
                        status="success",
                        details={"selected": "execute_agent"},
                    )
                    response, task_succeeded = await self._execute_agent(
                        user_id=user_id,
                        message=message,
                        user_language=user_language,
                        previous_context=previous_context,
                        execution_id=execution_id,
                    )
                if not response.strip():
                    intent["mode"] = CHAT_MODE

            if intent["mode"] == CHAT_MODE:
                self._emit_workflow_event(
                    execution_id=execution_id,
                    event_type="tool_selected",
                    node_id="tool_selector",
                    status="success",
                    details={"selected": "llm_chat"},
                )
                mem_search_start = time.perf_counter()
                self._emit_workflow_event(
                    execution_id=execution_id,
                    event_type="tool_execution_started",
                    node_id="memory_lookup",
                    status="running",
                    details={"phase": "semantic_search"},
                )
                related_memories = self.memory.search_memories(str(user_id), message, limit=5)
                self._log_stage_timing(user_id, "memory_lookup", mem_search_start, {"search_results": len(related_memories)})
                self._emit_workflow_event(
                    execution_id=execution_id,
                    event_type="tool_completed",
                    node_id="memory_lookup",
                    status="success",
                    details={
                        "phase": "semantic_search",
                        "search_results": len(related_memories),
                        "duration_ms": round((time.perf_counter() - mem_search_start) * 1000.0, 2),
                    },
                )
                live_context = self._build_live_context(message)
                prompt = self._build_reply_prompt(
                    user_id=str(user_id),
                    message=message,
                    language=user_language,
                    user_context=self.memory.get_context(str(user_id)),
                    group_context=[],
                    memories=related_memories,
                    live_context=live_context,
                )
                llm_messages = [
                    SystemMessage(
                        content=(
                            "You are HER. If user message is conversational, respond conversationally. "
                            "Answer the user's request first. Ask one clarification only if required. "
                            "Do not ask onboarding/profile questions unless user explicitly requests setup/config/reset. "
                            f"Respond strictly in language code {user_language}."
                        )
                    ),
                    HumanMessage(content=prompt),
                ]
                llm_start = time.perf_counter()
                self._emit_workflow_event(
                    execution_id=execution_id,
                    event_type="llm_started",
                    node_id="llm",
                    status="running",
                    details={
                        "provider": self._llm_provider,
                        "raw_messages": [str(getattr(msg, "content", "")) for msg in llm_messages],
                    },
                )
                response, used_fallback = self._generate_response_with_failover(llm_messages, user_id)
                token_budget = 500
                for idx, token in enumerate(re.findall(r"\\S+\\s*", response)):
                    if idx >= token_budget:
                        break
                    self._emit_workflow_event(
                        execution_id=execution_id,
                        event_type="llm_stream_token",
                        node_id="llm",
                        status="running",
                        details={"token": token},
                    )
                self._emit_workflow_event(
                    execution_id=execution_id,
                    event_type="llm_completed",
                    node_id="llm",
                    status="success" if response.strip() else "error",
                    details={
                        "used_fallback": used_fallback,
                        "duration_ms": round((time.perf_counter() - llm_start) * 1000.0, 2),
                    },
                )
                response = (response or "").strip() or "I am here with you."

        except Exception as exc:  # noqa: BLE001
            self._emit_workflow_event(
                execution_id=execution_id,
                event_type="error",
                node_id="response",
                status="error",
                details={"error": str(exc)},
            )
            logger.exception("API message handling failed for user %s: %s", user_id, exc)
            response = self._build_transient_llm_error_reply(exc)
            task_succeeded = False

        response = self._render_in_user_language(user_id, user_language, response)
        response = self._sanitize_response_for_policy(
            response=response,
            user_message=message,
            user_language=user_language,
            previous_assistant_message=previous_assistant_message,
        )
        self.memory.update_context(str(user_id), response, "assistant")
        if self._metrics:
            self._metrics.record_interaction(str(user_id), message, response)
        self._record_reinforcement(str(user_id), message, response, task_succeeded=task_succeeded)
        if previous_assistant_message:
            self._record_reinforcement(
                str(user_id),
                user_message=message,
                assistant_message=previous_assistant_message,
                task_succeeded=task_succeeded,
            )

        total_latency_ms = round((time.perf_counter() - request_started_at) * 1000.0, 2)
        self._emit_workflow_event(
            execution_id=execution_id,
            event_type="response_sent",
            node_id="response",
            status="success" if task_succeeded else "error",
            details={
                "response_preview": response[:500],
                "total_latency_ms": total_latency_ms,
                "debug": debug,
            },
        )
        self._decision_logger.log(
            event_type="assistant_response_api",
            summary="Handled API message with strict intent routing",
            user_id=str(user_id),
            source="api",
            details={
                "message_preview": message[:120],
                "language": user_language,
                "mode": intent["mode"],
                "action_confidence": intent["action_confidence"],
                "scheduled_tasks": schedule_count,
                "execution_id": execution_id,
            },
        )

        return {
            "execution_id": execution_id or "",
            "response": response,
            "mode": intent["mode"],
            "language": user_language,
            "scheduled_tasks": schedule_count,
            "task_succeeded": task_succeeded,
            "total_latency_ms": total_latency_ms,
            "debug": debug,
        }

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        user_timezone = self._persist_user_runtime_profile(
            user_id=user_id,
            chat_id=chat_id,
            username=getattr(update.effective_user, "username", None),
        )
        message = (update.message.text or "").strip()
        if not message:
            return
        execution_id = (
            self._workflow_event_hub.create_execution(user_id=str(user_id), message=message)
            if self._workflow_event_hub
            else None
        )
        request_started_at = time.perf_counter()
        self._emit_workflow_event(
            execution_id=execution_id,
            event_type="message_received",
            node_id="input",
            status="success",
            details={"message": message},
        )

        memory_start = time.perf_counter()
        self._emit_workflow_event(
            execution_id=execution_id,
            event_type="tool_execution_started",
            node_id="memory_lookup",
            status="running",
            details={"phase": "initial_context"},
        )
        previous_context = self.memory.get_context(str(user_id))
        previous_assistant_message = self._last_assistant_message(previous_context)
        self._log_stage_timing(user_id, "memory_lookup", memory_start, {"context_size": len(previous_context)})
        self._emit_workflow_event(
            execution_id=execution_id,
            event_type="tool_completed",
            node_id="memory_lookup",
            status="success",
            details={
                "phase": "initial_context",
                "duration_ms": round((time.perf_counter() - memory_start) * 1000.0, 2),
                "context_size": len(previous_context),
            },
        )

        is_group = self._is_group_chat(update)
        group_key = self._group_memory_key(chat_id)
        user_language = self._detect_user_language(message, user_id, previous_context)
        self._capture_profile_from_message(user_id, message, user_language)
        self._user_profiles.upsert_personalization_profile(user_id=user_id, preferred_language=user_language)
        autonomy_before = self._autonomy.get_profile(str(user_id))
        response_seconds = None
        if autonomy_before.last_proactive_at is not None:
            response_seconds = (datetime.now(UTC) - autonomy_before.last_proactive_at).total_seconds()
        autonomy_signals = self._autonomy.record_user_message(
            user_id=str(user_id),
            message=message,
            user_initiated=response_seconds is None or response_seconds >= 6 * 3600,
            response_seconds=response_seconds,
        )
        if bool(autonomy_signals.get("disabled")):
            self._user_profiles.upsert_personalization_profile(user_id=user_id, proactive_opt_out=True)
        elif "/unmute" in message.lower() or "enable proactive" in message.lower():
            self._user_profiles.upsert_personalization_profile(user_id=user_id, proactive_opt_out=False)

        if not self.is_admin(user_id) and not self.rate_limiter.is_allowed(user_id):
            await self._reply(
                update,
                self._render_in_user_language(user_id, user_language, "⏱️ Please slow down a bit!"),
            )
            return

        self.memory.update_context(str(user_id), message, "user")
        if is_group:
            self.memory.update_context(group_key, f"{update.effective_user.full_name}: {message}", "user", max_messages=120)

        if is_group and self.group_reply_on_mention_only and not self._message_mentions_bot(update):
            return

        try:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        except (TimedOut, NetworkError) as exc:
            logger.warning("Telegram typing indicator failed for chat %s: %s", chat_id, exc)

        intent = self._classify_intent(message)
        if self._requires_tool_execution(message):
            intent["mode"] = ACTION_MODE
            intent["action_confidence"] = 1.0
        self._emit_workflow_event(
            execution_id=execution_id,
            event_type="intent_detected",
            node_id="intent_classifier",
            status="success",
            details={
                "mode": intent["mode"],
                "action_confidence": intent["action_confidence"],
                "has_schedule_word": intent["has_schedule_word"],
            },
        )
        response = ""
        task_succeeded = True
        schedule_count = 0
        response_already_sent = False

        try:
            if intent["mode"] == ACTION_MODE:
                explicit_schedule = self._explicitly_requests_scheduling(message)
                if explicit_schedule and self.scheduler:
                    self._emit_workflow_event(
                        execution_id=execution_id,
                        event_type="tool_selected",
                        node_id="tool_selector",
                        status="success",
                        details={"selected": "scheduler"},
                    )
                    scheduler_start = time.perf_counter()
                    all_scheduled_tasks, _ = self._parse_multi_intent_schedule_with_llm(
                        message=message,
                        user_id=user_id,
                        chat_id=chat_id,
                        user_timezone=user_timezone,
                        language=user_language,
                        context_rows=previous_context,
                    )
                    response_parts: list[str] = []
                    created_task_count = 0
                    ok = True
                    details = "no tasks created"
                    if all_scheduled_tasks:
                        created_task_count = len(all_scheduled_tasks)
                        existing_names = {str(t.get("name", "")) for t in self.scheduler.get_tasks()}
                        for task in all_scheduled_tasks:
                            task_name = str(task.get("name", "task"))
                            if task_name in existing_names:
                                task_name = f"{task_name}_{int(datetime.now(UTC).timestamp())}"
                                task["name"] = task_name
                            existing_names.add(task_name)
                            self.scheduler.add_task(
                                name=task_name,
                                interval=str(task.get("interval", "once")),
                                task_type=str(task.get("type", "reminder")),
                                enabled=bool(task.get("enabled", True)),
                                **{k: v for k, v in task.items() if k not in {"name", "interval", "type", "enabled"}},
                            )
                            response_parts.append(
                                self._build_scheduler_confirmation(
                                    user_id=user_id,
                                    language=user_language,
                                    original_request=message,
                                    task=task,
                                    context_rows=previous_context,
                                )
                            )
                        ok, details = self.scheduler.persist_tasks()
                    else:
                        fallback_confirmation = self._maybe_schedule_from_message(
                            message=message,
                            user_id=user_id,
                            chat_id=chat_id,
                            user_timezone=user_timezone,
                        )
                        if fallback_confirmation:
                            response_parts.append(fallback_confirmation)
                            created_task_count = 1
                            ok, details = True, "created via deterministic fallback parser"
                        else:
                            ok, details = False, "could not infer a valid schedule task from request"
                    self._log_stage_timing(
                        user_id,
                        "scheduler",
                        scheduler_start,
                        {"created_tasks": created_task_count, "persisted": ok},
                    )
                    if not ok:
                        response_parts.append(f"Scheduler persistence is degraded: {details}")
                    response = "\n".join(part for part in response_parts if part).strip()
                    schedule_count = created_task_count
                    task_succeeded = ok and created_task_count > 0
                else:
                    self._emit_workflow_event(
                        execution_id=execution_id,
                        event_type="tool_selected",
                        node_id="tool_selector",
                        status="success",
                        details={"selected": "execute_agent"},
                    )
                    response, task_succeeded = await self._execute_agent(
                        user_id=user_id,
                        message=message,
                        user_language=user_language,
                        previous_context=previous_context,
                        execution_id=execution_id,
                    )
                if not response.strip():
                    intent["mode"] = CHAT_MODE

            if intent["mode"] == CHAT_MODE:
                self._emit_workflow_event(
                    execution_id=execution_id,
                    event_type="tool_selected",
                    node_id="tool_selector",
                    status="success",
                    details={"selected": "llm_chat"},
                )
                mem_search_start = time.perf_counter()
                self._emit_workflow_event(
                    execution_id=execution_id,
                    event_type="tool_execution_started",
                    node_id="memory_lookup",
                    status="running",
                    details={"phase": "semantic_search"},
                )
                related_memories = self.memory.search_memories(str(user_id), message, limit=5)
                self._log_stage_timing(user_id, "memory_lookup", mem_search_start, {"search_results": len(related_memories)})
                self._emit_workflow_event(
                    execution_id=execution_id,
                    event_type="tool_completed",
                    node_id="memory_lookup",
                    status="success",
                    details={
                        "phase": "semantic_search",
                        "search_results": len(related_memories),
                        "duration_ms": round((time.perf_counter() - mem_search_start) * 1000.0, 2),
                    },
                )
                group_context = self.memory.get_context(group_key) if is_group else []
                live_context = self._build_live_context(message)
                prompt = self._build_reply_prompt(
                    user_id=str(user_id),
                    message=message,
                    language=user_language,
                    user_context=self.memory.get_context(str(user_id)),
                    group_context=group_context,
                    memories=related_memories,
                    live_context=live_context,
                )
                llm_messages = [
                    SystemMessage(
                        content=(
                            "You are HER. If user message is conversational, respond conversationally. "
                            "Answer the user's request first. Ask one clarification only if required. "
                            "Do not ask onboarding/profile questions unless user explicitly requests setup/config/reset. "
                            f"Respond strictly in language code {user_language}."
                        )
                    ),
                    HumanMessage(content=prompt),
                ]
                response = await self._stream_chat_response(
                    update,
                    user_id,
                    llm_messages,
                    message,
                    user_language,
                    previous_assistant_message,
                    execution_id=execution_id,
                )
                response_already_sent = True
        except Exception as exc:  # noqa: BLE001
            self._emit_workflow_event(
                execution_id=execution_id,
                event_type="error",
                node_id="response",
                status="error",
                details={"error": str(exc)},
            )
            logger.exception("Message handling failed for user %s: %s", user_id, exc)
            await self._reply(update, self._build_transient_llm_error_reply(exc))
            return

        response = self._render_in_user_language(user_id, user_language, response)
        response = self._sanitize_response_for_policy(
            response=response,
            user_message=message,
            user_language=user_language,
            previous_assistant_message=previous_assistant_message,
        )
        if response and not response_already_sent:
            await self._reply_with_typing_effect(update, response[:3900])

        self.memory.update_context(str(user_id), response, "assistant")
        if is_group:
            self.memory.update_context(group_key, f"HER: {response}", "assistant", max_messages=120)
        if self._metrics:
            self._metrics.record_interaction(str(user_id), message, response)
        self._record_reinforcement(str(user_id), message, response, task_succeeded=task_succeeded)
        if previous_assistant_message:
            self._record_reinforcement(
                str(user_id),
                user_message=message,
                assistant_message=previous_assistant_message,
                task_succeeded=task_succeeded,
            )
        self._decision_logger.log(
            event_type="assistant_response",
            summary="Handled message with strict intent routing",
            user_id=str(user_id),
            source="telegram",
            details={
                "message_preview": message[:120],
                "language": user_language,
                "mode": intent["mode"],
                "action_confidence": intent["action_confidence"],
                "scheduled_tasks": schedule_count,
            },
        )
        self._emit_workflow_event(
            execution_id=execution_id,
            event_type="response_sent",
            node_id="response",
            status="success",
            details={
                "response_preview": response[:500],
                "total_latency_ms": round((time.perf_counter() - request_started_at) * 1000.0, 2),
            },
        )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        mapping = {
            "status": self.status_command,
            "personality": self.personality_command,
            "memories": self.memories_command,
            "reflect": self.reflect_command,
            "reset": self.reset_command,
            "mcp_status": self.mcp_command,
        }
        handler = mapping.get(query.data)
        if handler:
            await handler(update, context)
        else:
            await query.edit_message_text(f"Unhandled action: {query.data}")

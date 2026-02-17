import logging
import os
import re
from datetime import UTC, datetime, timedelta
import json
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

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
from utils.schedule_helpers import (
    extract_json_object,
    interval_unit_to_base,
    normalize_weekdays_input,
    parse_clock,
    parse_relative_delta,
)
from utils.scheduler import TaskScheduler

logger = logging.getLogger(__name__)
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
            max_steps=int(os.getenv("HER_AUTONOMOUS_MAX_STEPS", "16")),
            command_timeout_seconds=int(os.getenv("HER_SANDBOX_COMMAND_TIMEOUT_SECONDS", "60")),
            cpu_time_limit_seconds=int(os.getenv("HER_SANDBOX_CPU_TIME_LIMIT_SECONDS", "20")),
            memory_limit_mb=int(os.getenv("HER_SANDBOX_MEMORY_LIMIT_MB", "512")),
        )
        self._request_interpreter = None
        self._web_search_tool = CurlWebSearchTool()
        self._decision_logger = DecisionLogger()
        self._reinforcement = ReinforcementEngine()
        self._metrics: HERMetrics | None = None
        try:
            self._metrics = HERMetrics(
                host=os.getenv("REDIS_HOST", "redis"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                password=os.getenv("REDIS_PASSWORD", ""),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to initialize metrics recorder: %s", exc)

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
        sandbox = (caps.get("capabilities", {}) or {}).get("sandbox", {}) if caps else {}
        available = bool(sandbox.get("available"))
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

    def _normalize_ai_schedule_task(
        self,
        task: Any,
        user_id: int,
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
        if isinstance(notify_user_id, int):
            normalized["notify_user_id"] = notify_user_id
        elif str(notify_user_id or "").strip().isdigit():
            normalized["notify_user_id"] = int(str(notify_user_id).strip())
        else:
            normalized["notify_user_id"] = user_id

        run_at = str(task.get("run_at", "")).strip()
        if run_at:
            try:
                run_at_dt = datetime.fromisoformat(run_at.replace("Z", "+00:00"))
                if run_at_dt.tzinfo is None:
                    run_at_dt = run_at_dt.replace(tzinfo=UTC)
                normalized["run_at"] = run_at_dt.astimezone(UTC).isoformat()
            except ValueError:
                if interval == "once":
                    normalized["run_at"] = (now_utc + timedelta(minutes=5)).isoformat()

        at_value = str(task.get("at", "")).strip()
        if at_value and re.match(r"^\d{2}:\d{2}$", at_value):
            hour, minute = at_value.split(":", 1)
            if 0 <= int(hour) <= 23 and 0 <= int(minute) <= 59:
                normalized["at"] = at_value

        timezone_value = str(task.get("timezone", os.getenv("TZ", "UTC"))).strip() or "UTC"
        normalized["timezone"] = timezone_value

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
            "- For one-time reminders like 'in 5 minutes', provide run_at using current UTC time.\n"
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

        normalized_task = self._normalize_ai_schedule_task(payload.get("task"), user_id, message, now_utc)
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

    def _parse_schedule_request(self, message: str, user_id: int) -> tuple[dict[str, Any] | None, str | None]:
        if not self.scheduler:
            return None, None

        llm_task, llm_confirmation = self._parse_schedule_request_with_llm(message, user_id)
        if llm_task and llm_confirmation:
            return llm_task, llm_confirmation

        text = message.strip()
        lower = text.lower()
        now = datetime.now(UTC)
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
                    "timezone": os.getenv("TZ", "UTC"),
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
                    "message": reminder_body,
                    "notify_user_id": user_id,
                    "max_retries": 2,
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
                    "timezone": os.getenv("TZ", "UTC"),
                    "message": reminder_body,
                    "notify_user_id": user_id,
                    "max_retries": 2,
                    "retry_delay_seconds": 30,
                },
                "Got it. I'll remind you every day.",
            )

        # once a week / weekly
        if "once a week" in lower or "every week" in lower or "weekly" in lower:
            weekday = now.weekday()
            task_name = f"weekly_{self._slug(reminder_body)}_{user_id}"
            return (
                {
                    "name": task_name,
                    "type": "reminder",
                    "interval": "weekly",
                    "enabled": True,
                    "at": f"{clock[0]:02d}:{clock[1]:02d}",
                    "timezone": os.getenv("TZ", "UTC"),
                    "weekdays": [weekday],
                    "message": reminder_body,
                    "notify_user_id": user_id,
                    "max_retries": 2,
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
            run_at = now + delta
            task_name = f"once_{self._slug(reminder_body)}_{int(now.timestamp())}_{user_id}"
            return (
                {
                    "name": task_name,
                    "type": "reminder",
                    "interval": "once",
                    "one_time": True,
                    "enabled": True,
                    "run_at": run_at.isoformat(),
                    "timezone": os.getenv("TZ", "UTC"),
                    "message": reminder_body,
                    "notify_user_id": user_id,
                    "max_retries": 2,
                    "retry_delay_seconds": 30,
                },
                f"Got it. I'll remind you in {value} {normalized}.",
            )

        # tomorrow at X
        if "tomorrow" in lower and future_intent:
            target = (now + timedelta(days=1)).replace(hour=clock[0], minute=clock[1], second=0, microsecond=0)
            task_name = f"tomorrow_{self._slug(reminder_body)}_{int(now.timestamp())}_{user_id}"
            return (
                {
                    "name": task_name,
                    "type": "reminder",
                    "interval": "once",
                    "one_time": True,
                    "enabled": True,
                    "run_at": target.isoformat(),
                    "timezone": os.getenv("TZ", "UTC"),
                    "message": reminder_body,
                    "notify_user_id": user_id,
                    "max_retries": 2,
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
            days_ahead = (target_day - now.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            target = (now + timedelta(days=days_ahead)).replace(
                hour=clock[0],
                minute=clock[1],
                second=0,
                microsecond=0,
            )
            task_name = f"next_{day_match.group(1)}_{self._slug(reminder_body)}_{int(now.timestamp())}_{user_id}"
            return (
                {
                    "name": task_name,
                    "type": "reminder",
                    "interval": "once",
                    "one_time": True,
                    "enabled": True,
                    "run_at": target.isoformat(),
                    "timezone": os.getenv("TZ", "UTC"),
                    "message": reminder_body,
                    "notify_user_id": user_id,
                    "max_retries": 2,
                    "retry_delay_seconds": 30,
                },
                f"Got it. I'll remind you next {day_match.group(1).capitalize()}.",
            )

        return None, None

    def _maybe_schedule_from_message(self, message: str, user_id: int) -> str | None:
        if not self.scheduler:
            return None
        task, confirmation = self._parse_schedule_request(message, user_id)
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
        confirmation: str,
    ) -> str:
        if not self.scheduler:
            return "Scheduler is currently unavailable."
        payload_text = command[len("SCHEDULE ") :].strip()
        task_payload = extract_json_object(payload_text)
        if not task_payload:
            return "I could not parse a valid schedule payload from the interpreter output."

        now_utc = datetime.now(UTC)
        task = self._normalize_ai_schedule_task(task_payload, user_id, source_message, now_utc)
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

    def _maybe_handle_unified_request(self, message: str, user_id: int) -> str | None:
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

        needs_web_search = any(
            token in lower_msg
            for token in {"today", "current", "latest", "right now", "price", "news", "internet", "search"}
        )
        if needs_web_search:
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

        return (
            "You are HER, a warm emotionally intelligent assistant in Telegram. "
            "Answer naturally and concisely.\n\n"
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
            f"Adaptive communication profile: {style_summary}\n\n"
            f"Recent user context:\n{recent_user}\n\n"
            f"Recent group context:\n{recent_group}\n\n"
            f"Relevant long-term memories:\n{related_memory_text}\n\n"
            f"Real-time context:\n{live_context}\n\n"
            f"Current user message: {message}"
        )

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

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        message = (update.message.text or "").strip()
        if not message:
            return
        wants_utc_stamp = self._wants_utc_timestamp(message)
        previous_context = self.memory.get_context(str(user_id))
        previous_assistant_message = self._last_assistant_message(previous_context)

        is_group = self._is_group_chat(update)
        group_key = self._group_memory_key(chat_id)

        if not self.is_admin(user_id) and not self.rate_limiter.is_allowed(user_id):
            await self._reply(update, "⏱️ Please slow down a bit!")
            return

        self.memory.update_context(str(user_id), message, "user")

        if is_group:
            self.memory.update_context(group_key, f"{update.effective_user.full_name}: {message}", "user", max_messages=120)

        extracted_memories = self._extract_memories_from_message(message)
        for extracted in extracted_memories:
            self.memory.add_memory(str(user_id), extracted["text"], extracted["category"], extracted["importance"])
            if is_group:
                self.memory.add_memory(group_key, extracted["text"], "group_signal", extracted["importance"])
        if extracted_memories:
            try:
                self.personality_agent.adjust_trait(str(user_id), "emotional_depth", 1)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Personality adaptation skipped: %s", exc)

        if is_group:
            await self._summarize_group_if_needed(chat_id)

        should_reply = True
        if is_group and self.group_reply_on_mention_only:
            should_reply = self._message_mentions_bot(update)

        if not should_reply:
            return

        try:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        except (TimedOut, NetworkError) as exc:
            logger.warning("Telegram typing indicator failed for chat %s: %s", chat_id, exc)

        try:
            final_action = self._autonomous_operator.execute(message, user_id)
            response = json.dumps(final_action, ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Autonomous sandbox execution failed for user %s: %s", user_id, exc)
            response = json.dumps({"done": True, "result": "Autonomous execution failed."}, ensure_ascii=False)

        self.memory.update_context(str(user_id), response, "assistant")
        if is_group:
            self.memory.update_context(group_key, f"HER: {response}", "assistant", max_messages=120)
        if self._metrics:
            self._metrics.record_interaction(str(user_id), message, response)
        self._record_reinforcement(str(user_id), message, response, task_succeeded=True)
        if previous_assistant_message:
            # Evaluate user reaction to previous assistant message as evidence-based feedback.
            self._record_reinforcement(
                str(user_id),
                user_message=message,
                assistant_message=previous_assistant_message,
                task_succeeded=True,
            )
        self._decision_logger.log(
            event_type="assistant_response",
            summary="Generated autonomous JSON response",
            user_id=str(user_id),
            source="telegram",
            details={"message_preview": message[:120], "wants_utc_stamp": wants_utc_stamp},
        )
        await self._reply(update, response)

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

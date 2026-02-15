import logging
import os
from datetime import UTC, datetime
import json
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from langchain_core.messages import HumanMessage, SystemMessage
from telegram import MessageEntity, Update
from telegram.error import NetworkError, TimedOut
from telegram.ext import ContextTypes

from agents.personality_agent import PersonalityAgent
from her_mcp.tools import CurlWebSearchTool
from her_telegram.keyboards import get_admin_menu, get_personality_adjustment
from her_telegram.rate_limiter import RateLimiter
from memory.mem0_client import HERMemory
from utils.llm_factory import build_llm
from utils.metrics import HERMetrics
from utils.scheduler import TaskScheduler

logger = logging.getLogger(__name__)


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
        self._llm = build_llm()
        self._web_search_tool = CurlWebSearchTool()
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

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if self.is_admin(user_id):
            await self._reply(update, self.welcome_message, reply_markup=get_admin_menu())
            return
        await self._reply(update, self.welcome_message)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if self.is_admin(user_id):
            await self._reply(
                update,
                "Admin commands: /status /personality /memories /reflect /reset /mcp /schedule /help",
                reply_markup=get_admin_menu(),
            )
            return
        await self._reply(update, "Public commands: /start /help")

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
            lines = ["⏰ Scheduled tasks:"]
            for task in tasks:
                name = task.get("name", "unknown")
                task_type = task.get("type", "custom")
                interval = task.get("interval", "unknown")
                enabled = "on" if task.get("enabled", True) else "off"
                lines.append(f"- {name} | type={task_type} | interval={interval} | enabled={enabled}")
            lines.append("")
            lines.append("Use: /schedule set <task> <interval>")
            lines.append("Use: /schedule enable <task> | /schedule disable <task>")
            lines.append("Use: /schedule run <task>")
            lines.append("Use: /schedule add <name> <type> <interval> [key=value ...]")
            lines.append("Example: /schedule add any_rule workflow every_5_minutes source_url=https://example/api steps_json='[{\"action\":\"log\",\"message\":\"tick {now_utc}\"}]'")
            await self._reply(update, "\n".join(lines))
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
            summary = self._llm.invoke(
                [
                    SystemMessage(content="You extract durable memory summaries from chats."),
                    HumanMessage(content=prompt),
                ]
            )
            summary_text = (summary.content or "").strip() if summary else ""
            if summary_text:
                self.memory.add_memory(group_key, summary_text, "group_summary", 0.9)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to summarize group chat %s: %s", chat_id, exc)

    def _extract_memories_from_message(self, text: str) -> list[dict[str, Any]]:
        if not self.reflection_agent:
            return []
        try:
            return self.reflection_agent.analyze_conversation([{"role": "user", "message": text}])
        except Exception as exc:  # noqa: BLE001
            logger.debug("Reflection extraction skipped: %s", exc)
            return []


    def _build_live_context(self, message: str) -> str:
        now_utc = datetime.now(UTC)
        snippets = [f"Current UTC timestamp: {now_utc.isoformat()}"]
        lower_msg = message.lower()

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

        return "\n".join(snippets)

    def _build_reply_prompt(
        self,
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

        return (
            "You are HER, a warm emotionally intelligent assistant in Telegram. "
            "Answer naturally and concisely.\n\n"
            f"Recent user context:\n{recent_user}\n\n"
            f"Recent group context:\n{recent_group}\n\n"
            f"Relevant long-term memories:\n{related_memory_text}\n\n"
            f"Real-time context:\n{live_context}\n\n"
            f"Current user message: {message}"
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        message = (update.message.text or "").strip()
        if not message:
            return

        is_group = self._is_group_chat(update)
        group_key = self._group_memory_key(chat_id)

        if not self.is_admin(user_id) and not self.rate_limiter.is_allowed(user_id):
            await self._reply(update, "⏱️ Please slow down a bit!")
            return

        self.memory.update_context(str(user_id), message, "user")

        if is_group:
            self.memory.update_context(group_key, f"{update.effective_user.full_name}: {message}", "user", max_messages=120)

        for extracted in self._extract_memories_from_message(message):
            self.memory.add_memory(str(user_id), extracted["text"], extracted["category"], extracted["importance"])
            if is_group:
                self.memory.add_memory(group_key, extracted["text"], "group_signal", extracted["importance"])

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

        realtime_response = self._maybe_answer_realtime_query(message)
        if realtime_response:
            self.memory.update_context(str(user_id), realtime_response, "assistant")
            if is_group:
                self.memory.update_context(group_key, f"HER: {realtime_response}", "assistant", max_messages=120)
            if self._metrics:
                self._metrics.record_interaction(str(user_id), message, realtime_response)
            await self._reply(update, realtime_response)
            return

        memories = self.memory.search_memories(str(user_id), message, limit=5)
        if is_group:
            memories.extend(self.memory.search_memories(group_key, message, limit=5))

        user_context = self.memory.get_context(str(user_id))
        group_context = self.memory.get_context(group_key) if is_group else []
        live_context = self._build_live_context(message)
        prompt = self._build_reply_prompt(message, user_context, group_context, memories, live_context)

        try:
            response_obj = self._llm.invoke(
                [
                    SystemMessage(content="You are HER. Warm, empathetic, practical, concise."),
                    HumanMessage(content=prompt),
                ]
            )
            response = (response_obj.content or "").strip() if response_obj else ""
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to generate response for user %s: %s", user_id, exc)
            response = "I am here with you — I had a temporary issue generating a full reply."

        if not response:
            response = "I am here with you. Tell me a little more and I will help."

        self.memory.update_context(str(user_id), response, "assistant")
        if is_group:
            self.memory.update_context(group_key, f"HER: {response}", "assistant", max_messages=120)
        if self._metrics:
            self._metrics.record_interaction(str(user_id), message, response)
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

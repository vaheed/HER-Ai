import asyncio
import logging
import re
import time
from typing import Any
from typing import Final

from langchain_core.messages import HumanMessage, SystemMessage
from openai import APIConnectionError, APITimeoutError, RateLimitError
from telegram import Update
from telegram.error import NetworkError, TimedOut
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from config import AppConfig
from memory import FallbackMemory, HERMemory, RedisContextStore, initialize_database
from utils.llm_factory import build_llm
from utils.metrics import HERMetrics
from utils.retry import RetryError, with_retry
from utils.telegram_access import TelegramAccessController

WELCOME_MESSAGE: Final[str] = (
    "Hi! I'm HER ✨\n"
    "I can answer naturally now (not only acknowledgements), while keeping memory context."
)

logger = logging.getLogger("her-telegram")


def _is_shutdown_network_error(exc: NetworkError) -> bool:
    return "cannot schedule new futures after shutdown" in str(exc).lower()


def _build_user_prompt(user_text: str, context_messages: list[dict[str, str]], related_memories: list[dict[str, object]]) -> str:
    recent_context = "\n".join(
        f"- {item.get('role', 'user')}: {item.get('message', '')}" for item in context_messages[-8:]
    ) or "(none)"

    memory_lines: list[str] = []
    for memory in related_memories[:5]:
        memory_text = str(memory.get("memory") or memory.get("text") or memory.get("data") or memory)
        memory_lines.append(f"- {memory_text}")
    related_memory_text = "\n".join(memory_lines) or "(none)"

    return (
        "You are HER, a warm and emotionally intelligent personal AI companion. "
        "Respond naturally like a real conversational agent, not a system acknowledgement.\n\n"
        f"Recent conversation context:\n{recent_context}\n\n"
        f"Potentially relevant long-term memories:\n{related_memory_text}\n\n"
        f"User message: {user_text}\n\n"
        "Write a concise, empathetic reply. If clarification helps, ask one short follow-up question."
    )


def _extract_retry_after_seconds(message: str) -> int | None:
    match = re.search(r"try again in\s+(\d+)m([\d.]+)s", message.lower())
    if match:
        minutes = int(match.group(1))
        seconds = float(match.group(2))
        return max(1, int(minutes * 60 + seconds))

    match = re.search(r"retry after\s+(\d+)s", message.lower())
    if match:
        return max(1, int(match.group(1)))
    return None


def build_application(config: AppConfig, memory: HERMemory | Any, metrics: HERMetrics) -> Application:
    llm = build_llm()
    if not config.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is required to start the Telegram bot.")

    access = TelegramAccessController(
        host=config.redis_host,
        port=config.redis_port,
        password=config.redis_password,
        admin_user_ids=set(config.telegram_admin_user_ids),
        approval_required=config.telegram_public_approval_required,
        public_rate_limit_per_minute=config.telegram_public_rate_limit_per_minute,
    )

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text(WELCOME_MESSAGE)

    async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return

        admin_id = str(update.effective_user.id)
        if not access.is_admin(admin_id):
            await update.message.reply_text("Only admins can approve users.")
            return

        if not context.args:
            await update.message.reply_text("Usage: /approve <telegram_user_id>")
            return

        target_user_id = context.args[0].strip()
        access.approve_user(target_user_id)
        await update.message.reply_text(f"Approved user `{target_user_id}` for public chat access.", parse_mode="Markdown")

    async def mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return

        user_id = str(update.effective_user.id)
        role = "admin" if access.is_admin(user_id) else "public"
        approved = access.is_approved(user_id)
        await update.message.reply_text(
            (
                f"Mode: {role}\n"
                f"Approved: {'yes' if approved else 'no'}\n"
                f"Public approval required: {'yes' if config.telegram_public_approval_required else 'no'}\n"
                f"Public rate limit: {config.telegram_public_rate_limit_per_minute} msg/min"
            )
        )

    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return

        user = update.effective_user
        user_id = str(user.id) if user else "unknown"
        message_text = (update.message.text or "").strip()
        if not message_text:
            await update.message.reply_text("I didn't catch that. Could you send your message again?")
            return

        can_send, reason = access.can_send_message(user_id)
        if not can_send and reason == "not_approved":
            await update.message.reply_text(
                "You're in public mode and need admin approval before we can chat. "
                "Ask an admin to run /approve <your_telegram_user_id>."
            )
            return
        if not can_send and reason == "rate_limited":
            await update.message.reply_text(
                "You're sending messages too quickly right now. Please wait a minute and try again."
            )
            return

        memory.update_context(user_id, message_text, "user")
        memory.add_memory(user_id, message_text, "telegram_message", 0.5)

        related_memories = memory.search_memories(user_id, message_text, limit=5)
        context_messages = memory.get_context(user_id)

        try:
            prompt = _build_user_prompt(message_text, context_messages, related_memories)
            llm_response = with_retry(
                lambda: llm.invoke(
                    [
                        SystemMessage(
                            content=(
                                "You are HER. Be warm, emotionally aware, and practical. "
                                "Do not expose system internals."
                            )
                        ),
                        HumanMessage(content=prompt),
                    ]
                ),
                attempts=2,
                delay_seconds=1.0,
                retry_on=(RateLimitError, APITimeoutError, APIConnectionError),
            )
            response = (llm_response.content or "").strip() if llm_response else ""
            if not response:
                response = "I'm here with you. Tell me a bit more so I can help thoughtfully."
        except RetryError as exc:
            cause = exc.__cause__ or exc
            retry_after = _extract_retry_after_seconds(str(cause))
            if retry_after is not None:
                response = (
                    f"I'm temporarily rate-limited by the model provider. "
                    f"Please retry in about {retry_after} seconds and I'll respond right away."
                )
            else:
                response = (
                    "I'm having temporary trouble reaching the model provider. "
                    "Please retry in a few moments."
                )
            logger.warning("Transient LLM failure for user %s: %s", user_id, cause)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to generate LLM reply for user %s: %s", user_id, exc)
            response = (
                "I'm here with you. I hit a temporary issue generating a full response, "
                "but I saved your message and can keep going."
            )

        memory.update_context(user_id, response, "assistant")
        metrics.record_interaction(user_id, message_text, response)
        logger.info("Replied to user %s", user_id)
        await update.message.reply_text(response)

    application = Application.builder().token(config.telegram_bot_token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("approve", approve))
    application.add_handler(CommandHandler("mode", mode))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return application


def run_bot() -> None:
    logging.basicConfig(level=logging.INFO)
    config = AppConfig()

    try:
        initialize_database(config)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Database initialization failed; continuing with degraded memory mode: %s", exc)

    redis_store = RedisContextStore(
        host=config.redis_host,
        port=config.redis_port,
        password=config.redis_password,
        ttl_seconds=86400,
    )
    try:
        memory = HERMemory(config, redis_store)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Long-term memory unavailable; using in-process fallback memory: %s", exc)
        memory = FallbackMemory()
    metrics = HERMetrics(
        host=config.redis_host,
        port=config.redis_port,
        password=config.redis_password,
    )

    while True:
        app = build_application(config, memory, metrics)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            app.run_polling(
                allowed_updates=Update.ALL_TYPES,
                close_loop=False,
                stop_signals=None,
            )
            return
        except (TimedOut, NetworkError) as exc:
            if isinstance(exc, NetworkError) and _is_shutdown_network_error(exc):
                logger.info("Telegram polling stopped during runtime shutdown; exiting bot loop cleanly.")
                return
            logger.warning(
                "Telegram startup failed (%s). Retrying in %s seconds.",
                exc.__class__.__name__,
                config.telegram_startup_retry_delay_seconds,
            )
            time.sleep(config.telegram_startup_retry_delay_seconds)

import asyncio
import logging
import time
from typing import Final

from langchain_core.messages import HumanMessage, SystemMessage
from telegram import Update
from telegram.error import NetworkError, TimedOut
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from config import AppConfig
from memory import HERMemory, RedisContextStore, initialize_database
from utils.llm_factory import build_llm
from utils.metrics import HERMetrics

WELCOME_MESSAGE: Final[str] = (
    "Hi! I'm HER ✨\n"
    "I can answer naturally now (not only acknowledgements), while keeping memory context."
)

logger = logging.getLogger("her-telegram")


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


def build_application(config: AppConfig, memory: HERMemory, metrics: HERMetrics) -> Application:
    llm = build_llm()
    if not config.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is required to start the Telegram bot.")

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text(WELCOME_MESSAGE)

    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return

        user = update.effective_user
        user_id = str(user.id) if user else "unknown"
        message_text = (update.message.text or "").strip()
        if not message_text:
            await update.message.reply_text("I didn't catch that. Could you send your message again?")
            return

        memory.update_context(user_id, message_text, "user")
        memory.add_memory(user_id, message_text, "telegram_message", 0.5)

        related_memories = memory.search_memories(user_id, message_text, limit=5)
        context_messages = memory.get_context(user_id)

        try:
            prompt = _build_user_prompt(message_text, context_messages, related_memories)
            llm_response = llm.invoke(
                [
                    SystemMessage(
                        content=(
                            "You are HER. Be warm, emotionally aware, and practical. "
                            "Do not expose system internals."
                        )
                    ),
                    HumanMessage(content=prompt),
                ]
            )
            response = (llm_response.content or "").strip() if llm_response else ""
            if not response:
                response = "I'm here with you. Tell me a bit more so I can help thoughtfully."
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
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return application


def run_bot() -> None:
    logging.basicConfig(level=logging.INFO)
    config = AppConfig()

    initialize_database(config)

    redis_store = RedisContextStore(
        host=config.redis_host,
        port=config.redis_port,
        password=config.redis_password,
        ttl_seconds=86400,
    )
    memory = HERMemory(config, redis_store)
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
            logger.warning(
                "Telegram startup failed (%s). Retrying in %s seconds.",
                exc.__class__.__name__,
                config.telegram_startup_retry_delay_seconds,
            )
            time.sleep(config.telegram_startup_retry_delay_seconds)

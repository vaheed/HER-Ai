import asyncio
import logging
from typing import Final

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from config import AppConfig
from memory import HERMemory, RedisContextStore, initialize_database
from utils.metrics import HERMetrics

WELCOME_MESSAGE: Final[str] = (
    "Hi! I'm HER. The core systems are running and ready for Telegram testing.\n"
    "Send a message and I'll acknowledge it while logging context."
)

logger = logging.getLogger("her-telegram")


def build_application(config: AppConfig, memory: HERMemory, metrics: HERMetrics) -> Application:
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
        message_text = update.message.text or ""

        memory.update_context(user_id, message_text, "user")
        memory.add_memory(user_id, message_text, "telegram_message", 0.5)

        response = (
            "✅ HER received your message and saved it to memory.\n\n"
            f"*User ID*: `{user_id}`\n"
            f"*Message*: {message_text}"
        )
        metrics.record_interaction(user_id, message_text, response)
        logger.info("Logged interaction for user %s", user_id)
        await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)

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

    app = build_application(config, memory, metrics)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        close_loop=False,
        stop_signals=None,
    )

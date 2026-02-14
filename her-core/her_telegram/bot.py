import logging

from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from her_telegram.handlers import MessageHandlers

logger = logging.getLogger(__name__)


class HERBot:
    """Main Telegram bot application."""

    def __init__(
        self,
        token: str,
        conversation_agent,
        memory,
        personality_agent,
        reflection_agent,
        admin_user_ids: list,
        rate_limiter,
        mcp_manager=None,
        welcome_message: str = "Hi! I'm HER, your AI companion. How can I help you today?",
        group_reply_on_mention_only: bool = True,
        group_summary_every_messages: int = 25,
    ):
        self.token = token
        self.handlers = MessageHandlers(
            conversation_agent=conversation_agent,
            memory=memory,
            personality_agent=personality_agent,
            admin_user_ids=admin_user_ids,
            rate_limiter=rate_limiter,
            mcp_manager=mcp_manager,
            reflection_agent=reflection_agent,
            welcome_message=welcome_message,
            group_reply_on_mention_only=group_reply_on_mention_only,
            group_summary_every_messages=group_summary_every_messages,
        )
        self.reflection_agent = reflection_agent
        self.app = None

    async def start(self):
        self.app = (
            Application.builder()
            .token(self.token)
            .connect_timeout(20.0)
            .read_timeout(30.0)
            .write_timeout(30.0)
            .pool_timeout(20.0)
            .build()
        )

        self.app.add_handler(CommandHandler("start", self.handlers.start_command))
        self.app.add_handler(CommandHandler("help", self.handlers.help_command))
        self.app.add_handler(CommandHandler("status", self.handlers.status_command))
        self.app.add_handler(CommandHandler("personality", self.handlers.personality_command))
        self.app.add_handler(CommandHandler("memories", self.handlers.memories_command))
        self.app.add_handler(CommandHandler("reflect", self.handlers.reflect_command))
        self.app.add_handler(CommandHandler("reset", self.handlers.reset_command))
        self.app.add_handler(CommandHandler("mcp", self.handlers.mcp_command))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handlers.handle_message))
        self.app.add_handler(CallbackQueryHandler(self.handlers.handle_callback))

        logger.info("Starting Telegram bot...")
        await self.app.initialize()
        me = await self.app.bot.get_me()
        self.handlers.set_bot_username(me.username)
        await self.app.start()
        await self.app.updater.start_polling()
        logger.info("✓ Telegram bot is running!")

    async def stop(self):
        if self.app:
            logger.info("Stopping Telegram bot...")
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()

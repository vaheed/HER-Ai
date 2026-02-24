from __future__ import annotations

import asyncio

from her.config.settings import get_settings
from her.interfaces.api.main import create_app
from her.interfaces.telegram_bot import TelegramBotInterface


async def main() -> None:
    """Run Telegram bot using the same runtime graph as API app."""

    settings = get_settings()
    app = create_app()

    async with app.router.lifespan_context(app):
        bot = TelegramBotInterface(
            token=settings.telegram_bot_token,
            orchestrator=app.state.orchestrator,
            reflection_agent=app.state.reflection_agent,
            memory_store=app.state.memory_store,
            personality_manager=app.state.personality_manager,
        )
        await bot.start()


if __name__ == "__main__":
    asyncio.run(main())

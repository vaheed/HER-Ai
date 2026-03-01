from __future__ import annotations

import asyncio
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from her.agents.orchestrator import AgentOrchestrator
from her.agents.reflection import ReflectionAgent
from her.memory.store import MemoryStore
from her.personality.manager import PersonalityManager


class TelegramBotInterface:
    """Telegram bot runtime with command and message handlers."""

    def __init__(
        self,
        token: str,
        orchestrator: AgentOrchestrator,
        reflection_agent: ReflectionAgent,
        memory_store: MemoryStore,
        personality_manager: PersonalityManager,
    ) -> None:
        self._token = token
        self._orchestrator = orchestrator
        self._reflection = reflection_agent
        self._memory_store = memory_store
        self._personality = personality_manager
        self._application: Any | None = None

    def build_application(self) -> Any:
        """Build and configure Telegram application handlers."""

        if not self._token:
            raise ValueError("TELEGRAM_BOT_TOKEN is not configured")

        app = ApplicationBuilder().token(self._token).build()
        app.add_handler(CommandHandler("reflect", self._handle_reflect))
        app.add_handler(CommandHandler("goals", self._handle_goals))
        app.add_handler(CommandHandler("mood", self._handle_mood))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))
        self._application = app
        return app

    async def start(self) -> None:
        """Start Telegram polling loop."""

        app = self._application or self.build_application()
        await asyncio.to_thread(app.run_polling, close_loop=False)

    async def _handle_reflect(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        vector = await self._reflection.run_daily_reflection()
        message = update.effective_message
        if message is None:
            return

        await message.reply_text(
            "Reflection completed. Updated personality:\n"
            f"curiosity={vector.curiosity:.2f}, warmth={vector.warmth:.2f}, directness={vector.directness:.2f}"
        )

    async def _handle_goals(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        message = update.effective_message
        if message is None:
            return

        goals = await self._memory_store.list_active_goals(limit=8)
        if not goals:
            await message.reply_text("No active goals right now.")
            return

        lines = [f"- {goal.description} (priority={goal.priority:.2f})" for goal in goals]
        await message.reply_text("Active goals:\n" + "\n".join(lines))

    async def _handle_mood(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        message = update.effective_message
        if message is None:
            return

        emotion = self._personality.current_emotion
        vector = self._personality.current_personality
        await message.reply_text(
            "Current mood state:\n"
            f"emotion={emotion.state} intensity={emotion.intensity:.2f}\n"
            f"warmth={vector.warmth:.2f} empathy={vector.empathy:.2f} directness={vector.directness:.2f}"
        )

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        message = update.effective_message
        chat = update.effective_chat
        if message is None or chat is None:
            return

        text = (message.text or "").strip()
        if not text:
            await message.reply_text("Please send a non-empty message.")
            return

        session_id = _session_id_for_chat(chat.id)
        trace_id = f"tg-{update.update_id}"

        response = await self._orchestrator.handle_interaction(
            session_id=session_id,
            content=text,
            trace_id=trace_id,
        )
        await message.reply_text(response.content)


def _session_id_for_chat(chat_id: int) -> UUID:
    return uuid5(NAMESPACE_URL, f"telegram:{chat_id}")

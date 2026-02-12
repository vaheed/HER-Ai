import logging
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

from agents.personality_agent import PersonalityAgent
from memory.mem0_client import HERMemory
from her_telegram.keyboards import get_admin_menu, get_personality_adjustment
from her_telegram.rate_limiter import RateLimiter

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
        reflection_agent: Any | None = None,
        welcome_message: str = "Hi! I'm HER, your AI companion. How can I help you today?",
    ):
        self.conversation_agent = conversation_agent
        self.memory = memory
        self.personality_agent = personality_agent
        self.admin_user_ids = admin_user_ids
        self.rate_limiter = rate_limiter
        self.mcp_manager = mcp_manager
        self.reflection_agent = reflection_agent
        self.welcome_message = welcome_message

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_user_ids

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if self.is_admin(user_id):
            await update.message.reply_text(self.welcome_message, reply_markup=get_admin_menu())
            return
        await update.message.reply_text(self.welcome_message)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if self.is_admin(user_id):
            await update.message.reply_text(
                "Admin commands: /status /personality /memories /reflect /reset /mcp /help",
                reply_markup=get_admin_menu(),
            )
            return
        await update.message.reply_text("Public commands: /start /help")

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Admin only command")
            return

        status_lines = ["📊 HER Status"]
        if self.mcp_manager:
            mcp_status = self.mcp_manager.get_server_status()
            status_lines.append(f"MCP: {mcp_status}")
        await update.message.reply_text("\n".join(status_lines))

    async def personality_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Admin only command")
            return
        await update.message.reply_text("Adjust personality traits:", reply_markup=get_personality_adjustment())

    async def memories_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Admin only command")
            return

        user_id = str(update.effective_user.id)
        context_messages = self.memory.get_context(user_id)
        await update.message.reply_text(f"Recent context entries: {len(context_messages)}")

    async def reflect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Admin only command")
            return
        await update.message.reply_text("🔄 Reflection triggered (placeholder)")

    async def reset_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Admin only command")
            return
        self.rate_limiter.reset_user(update.effective_user.id)
        await update.message.reply_text("🗑️ Context reset complete (rate-limit bucket reset).")

    async def mcp_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Admin only command")
            return
        status = self.mcp_manager.get_server_status() if self.mcp_manager else {"mcp": "not configured"}
        await update.message.reply_text(f"🔧 MCP status:\n{status}")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        message = update.message.text

        if not self.is_admin(user_id) and not self.rate_limiter.is_allowed(user_id):
            await update.message.reply_text("⏱️ Please slow down a bit!")
            return

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        self.memory.update_context(str(user_id), message, "user")
        response = f"I heard you: {message}"
        self.memory.update_context(str(user_id), response, "assistant")
        await update.message.reply_text(response)

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

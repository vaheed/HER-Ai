from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_admin_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("📊 Status", callback_data="status"),
            InlineKeyboardButton("🎭 Personality", callback_data="personality"),
        ],
        [
            InlineKeyboardButton("💭 Memories", callback_data="memories"),
            InlineKeyboardButton("🔄 Reflect", callback_data="reflect"),
        ],
        [
            InlineKeyboardButton("🔧 MCP Servers", callback_data="mcp_status"),
            InlineKeyboardButton("🗑️ Reset Context", callback_data="reset"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_personality_adjustment() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("❤️ Warmth", callback_data="trait_warmth"),
            InlineKeyboardButton("🤔 Curiosity", callback_data="trait_curiosity"),
        ],
        [
            InlineKeyboardButton("💪 Assertiveness", callback_data="trait_assertiveness"),
            InlineKeyboardButton("😄 Humor", callback_data="trait_humor"),
        ],
        [InlineKeyboardButton("🌊 Emotional Depth", callback_data="trait_emotional_depth")],
        [InlineKeyboardButton("⬅️ Back", callback_data="admin_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)

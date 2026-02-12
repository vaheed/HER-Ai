import asyncio
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import yaml
from dotenv import load_dotenv

from agents import ConversationAgent, PersonalityAgent, ReflectionAgent
from config import AppConfig
from mcp.manager import MCPManager
from mcp.tools import MCPToolsIntegration
from memory import HERMemory, RedisContextStore, initialize_database
from telegram.bot import HERBot
from telegram.rate_limiter import RateLimiter


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "ok"}')


def start_health_server() -> None:
    server = HTTPServer(("0.0.0.0", 8000), HealthHandler)
    server.serve_forever()


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("her-main")


async def async_main(config: AppConfig) -> None:
    logger.info("🚀 Starting HER AI Assistant...")

    logger.info("Initializing memory system...")
    redis_store = RedisContextStore(
        host=config.redis_host,
        port=config.redis_port,
        password=config.redis_password,
        ttl_seconds=86400,
    )
    initialize_database(config)
    memory = HERMemory(config, redis_store)
    logger.info("✓ Memory system initialized")

    logger.info("Initializing MCP servers...")
    mcp_manager = MCPManager()
    await mcp_manager.initialize()
    status = mcp_manager.get_server_status()
    logger.info("✓ MCP servers started: %s", status)

    logger.info("Creating MCP tools...")
    mcp_tools = MCPToolsIntegration(mcp_manager)
    tools = mcp_tools.create_curated_tools()
    logger.info("✓ Created %s tools", len(tools))

    agents_config = Path("/app/config/agents.yaml")
    personality_config = Path("/app/config/personality.yaml")

    logger.info("Initializing agents...")
    conversation_agent = ConversationAgent(agents_config).build(tools=tools)
    reflection_agent = ReflectionAgent(agents_config).build()
    personality_manager = PersonalityAgent(agents_config, personality_config)
    personality_agent = personality_manager.build()
    logger.info("✓ Agents initialized")

    with open("config/telegram.yaml", "r", encoding="utf-8") as handle:
        telegram_config = yaml.safe_load(handle) or {}
    with open("config/rate_limits.yaml", "r", encoding="utf-8") as handle:
        rate_config = yaml.safe_load(handle) or {}

    rate_limiter = RateLimiter(
        messages_per_minute=rate_config["public_users"]["messages_per_minute"],
        messages_per_hour=rate_config["public_users"]["messages_per_hour"],
    )

    admin_user_ids = telegram_config.get("bot", {}).get("admin_user_ids") or []
    env_admin = os.getenv("ADMIN_USER_ID")
    if env_admin and env_admin.isdigit() and int(env_admin) not in admin_user_ids:
        admin_user_ids.append(int(env_admin))

    bot = HERBot(
        token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        conversation_agent=conversation_agent,
        memory=memory,
        personality_agent=personality_agent,
        reflection_agent=reflection_agent,
        admin_user_ids=admin_user_ids,
        rate_limiter=rate_limiter,
        mcp_manager=mcp_manager,
        welcome_message=telegram_config.get("bot", {}).get("features", {}).get(
            "welcome_message", "Hi! I'm HER, your AI companion. How can I help you today?"
        ),
    )

    if config.telegram_enabled and config.telegram_bot_token:
        await bot.start()
    elif not config.telegram_enabled:
        logger.info("Telegram bot disabled via TELEGRAM_ENABLED=false")
    else:
        logger.warning("Telegram bot token is missing; running without Telegram polling")

    logger.info("🎉 HER is fully operational!")
    logger.info("📱 Telegram bot is listening for messages")
    logger.info("👨‍💼 Admin users: %s", admin_user_ids)

    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await bot.stop()
        await mcp_manager.stop_all_servers()

    # compatibility with phase-1 smoke checks
    if config.startup_warmup_enabled:
        personality_manager.adjust_trait("demo-user", "warmth", 1)


def main() -> None:
    load_dotenv()
    config = AppConfig()
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    asyncio.run(async_main(config))


if __name__ == "__main__":
    main()

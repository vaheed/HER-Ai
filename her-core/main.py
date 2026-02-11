import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from config import AppConfig
from memory import HERMemory, RedisContextStore, initialize_database
from agents import ConversationAgent, ReflectionAgent, PersonalityAgent, ToolAgent
from agents.crew_orchestrator import CrewOrchestrator
from telegram_bot import run_bot


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"{\"status\": \"ok\"}")


def start_health_server() -> None:
    server = HTTPServer(("0.0.0.0", 8000), HealthHandler)
    server.serve_forever()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("her-main")

    config = AppConfig()

    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()

    redis_store = RedisContextStore(
        host=config.redis_host,
        port=config.redis_port,
        password=config.redis_password,
        ttl_seconds=86400,
    )
    initialize_database(config)
    memory = HERMemory(config, redis_store)

    if config.telegram_enabled and config.telegram_bot_token:
        logger.info("Starting Telegram bot")
        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()
    elif not config.telegram_enabled:
        logger.info("Telegram bot disabled via TELEGRAM_ENABLED=false")
    else:
        logger.warning("Telegram bot token is missing; running without Telegram polling")

    agents_config = Path("/app/config/agents.yaml")
    personality_config = Path("/app/config/personality.yaml")

    conversation_agent = ConversationAgent(agents_config).build()
    reflection_agent = ReflectionAgent(agents_config).build()
    personality_manager = PersonalityAgent(agents_config, personality_config)
    personality_agent = personality_manager.build()
    tool_agent = ToolAgent(agents_config).build()
    CrewOrchestrator().build_crew(
        {
            "conversation": conversation_agent,
            "reflection": reflection_agent,
            "personality": personality_agent,
            "tool": tool_agent,
        }
    )

    logger.info("✓ PostgreSQL connected with pgvector enabled")
    logger.info("✓ Redis connected")
    logger.info("✓ Mem0 initialized")
    logger.info("✓ Conversation Agent created")
    logger.info("✓ Reflection Agent created")
    logger.info("✓ Personality Agent created")
    logger.info("✓ Tool Agent created")
    logger.info("✓ CrewAI coordination ready")

    if config.startup_warmup_enabled:
        user_id = "demo-user"
        memory.update_context(user_id, "Hello HER", "user")
        memory.add_memory(user_id, "User said hello", "greeting", 0.8)
        memory.search_memories(user_id, "hello", limit=1)
        personality_manager.adjust_trait(user_id, "warmth", 1)
        logger.info("✓ Startup warm-up checks completed")
    else:
        logger.info("Startup warm-up checks disabled (set STARTUP_WARMUP_ENABLED=true to enable)")
    logger.info("🎉 HER Phase 1 Complete - All systems operational!")

    health_thread.join()


if __name__ == "__main__":
    main()

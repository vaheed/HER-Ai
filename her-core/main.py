import asyncio
import json
import logging
import os
import stat
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
import yaml
from dotenv import load_dotenv

from agents import ConversationAgent, PersonalityAgent, ReflectionAgent
from api_adapter import OpenAPIAdapterServer
from config import AppConfig
from her_mcp.manager import MCPManager
from her_mcp.tools import MCPToolsIntegration
from memory import FallbackMemory, HERMemory, RedisContextStore, initialize_database
from her_telegram.bot import HERBot
from her_telegram.rate_limiter import RateLimiter
from utils.config_paths import resolve_config_file
from utils.scheduler import get_scheduler
from workflow import WorkflowEventHub, WorkflowServer


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "ok"}')


def start_health_server() -> None:
    server = HTTPServer(("0.0.0.0", 8000), HealthHandler)
    server.serve_forever()


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("her-main")

# Custom handler to log to Redis for dashboard
class RedisLogHandler(logging.Handler):
    """Log handler that writes to Redis for dashboard visibility."""

    def __init__(self, redis_host: str, redis_port: int, redis_password: str):
        super().__init__()
        try:
            import redis
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                password=redis_password,
                decode_responses=True,
            )
        except Exception:
            self.redis_client = None

    def emit(self, record):
        if not self.redis_client:
            return
        try:
            import json
            from datetime import datetime, timezone

            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "name": record.name,
                "message": record.getMessage(),
            }
            self.redis_client.lpush("her:logs", json.dumps(log_entry))
            self.redis_client.ltrim("her:logs", 0, 199)
        except Exception:
            pass  # Silently fail if Redis unavailable


# Add Redis log handler if Redis is available
try:
    redis_log_handler = RedisLogHandler(
        redis_host=os.getenv("REDIS_HOST", "redis"),
        redis_port=int(os.getenv("REDIS_PORT", "6379")),
        redis_password=os.getenv("REDIS_PASSWORD", ""),
    )
    redis_log_handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(redis_log_handler)
except Exception:
    pass  # Continue without Redis logging if unavailable


async def async_main(config: AppConfig) -> None:
    logger.info("🚀 Starting HER AI Assistant...")
    _log_runtime_config_selection()

    logger.info("Initializing memory system...")
    redis_store = RedisContextStore(
        host=config.redis_host,
        port=config.redis_port,
        password=config.redis_password,
        ttl_seconds=86400,
    )
    try:
        initialize_database(config)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Database initialization failed; continuing with degraded memory mode: %s", exc)

    try:
        memory = HERMemory(config, redis_store)
        logger.info("✓ Memory system initialized")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Long-term memory unavailable; using in-process fallback memory: %s", exc)
        memory = FallbackMemory()

    mcp_manager = None
    status: dict[str, dict[str, str]] = {}
    logger.info("Initializing MCP servers...")
    mcp_config_path = os.getenv("MCP_CONFIG_PATH", "mcp_servers.yaml")
    try:
        mcp_manager = MCPManager(config_path=mcp_config_path)
        await mcp_manager.initialize()
        status = mcp_manager.get_server_status()
        logger.info("✓ MCP servers started from '%s': %s", mcp_config_path, status)
    except Exception as exc:  # noqa: BLE001
        logger.exception("MCP bootstrap failed; continuing without MCP servers: %s", exc)
        mcp_manager = None
        status = {"mcp": {"status": "failed", "message": f"bootstrap error: {exc}"}}

    logger.info("Creating MCP tools...")
    try:
        if mcp_manager is None:
            tools = []
            mcp_tools = None
        else:
            mcp_tools = MCPToolsIntegration(mcp_manager)
            tools = mcp_tools.create_curated_tools()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Tool integration failed; falling back to no-tool mode: %s", exc)
        tools = []
        mcp_tools = None
    logger.info("✓ Created %s tools", len(tools))
    capability_snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool_count": len(tools),
        "capabilities": mcp_tools.get_capability_status() if mcp_tools else {},
        "mcp_servers": status,
    }
    _log_degraded_capabilities(capability_snapshot)
    _publish_runtime_capabilities(config, capability_snapshot)

    agents_config = resolve_config_file("agents.yaml")
    personality_config = resolve_config_file("personality.yaml")

    logger.info("Initializing agents...")
    conversation_agent = ConversationAgent(agents_config).build(tools=tools)
    reflection_agent = ReflectionAgent(agents_config).build()
    personality_manager = PersonalityAgent(agents_config, personality_config)
    personality_agent = personality_manager.build()
    logger.info("✓ Agents initialized")

    workflow_hub: WorkflowEventHub | None = None
    workflow_server: WorkflowServer | None = None
    api_adapter_server: OpenAPIAdapterServer | None = None
    if config.workflow_debug_server_enabled:
        workflow_hub = WorkflowEventHub()
        workflow_server = WorkflowServer(
            event_hub=workflow_hub,
            host=config.workflow_debug_host,
            port=config.workflow_debug_port,
        )
        await workflow_server.start()

    with resolve_config_file("telegram.yaml").open("r", encoding="utf-8") as handle:
        telegram_config = yaml.safe_load(handle) or {}
    with resolve_config_file("rate_limits.yaml").open("r", encoding="utf-8") as handle:
        rate_config = yaml.safe_load(handle) or {}

    rate_limiter = RateLimiter(
        messages_per_minute=rate_config["public_users"]["messages_per_minute"],
        messages_per_hour=rate_config["public_users"]["messages_per_hour"],
    )

    admin_user_ids = telegram_config.get("bot", {}).get("admin_user_ids") or []
    env_admin = os.getenv("ADMIN_USER_ID")
    if env_admin and env_admin.isdigit() and int(env_admin) not in admin_user_ids:
        admin_user_ids.append(int(env_admin))

    features = telegram_config.get("bot", {}).get("features", {})
    scheduler = get_scheduler()

    bot = HERBot(
        token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        conversation_agent=conversation_agent,
        memory=memory,
        personality_agent=personality_agent,
        reflection_agent=reflection_agent,
        admin_user_ids=admin_user_ids,
        rate_limiter=rate_limiter,
        mcp_manager=mcp_manager,
        scheduler=scheduler,
        welcome_message=features.get(
            "welcome_message", "Hi! I'm HER, your AI companion. How can I help you today?"
        ),
        group_reply_on_mention_only=features.get("group_reply_on_mention_only", True),
        group_summary_every_messages=features.get("group_summary_every_messages", 25),
        workflow_event_hub=workflow_hub,
    )
    if config.api_adapter_enabled:
        api_adapter_server = OpenAPIAdapterServer(
            handler=bot.handlers.process_message_api,
            host=config.api_adapter_host,
            port=config.api_adapter_port,
            bearer_token=config.api_adapter_bearer_token,
            model_name=config.api_adapter_model_name,
        )
        await api_adapter_server.start()

    # Start task scheduler
    await scheduler.start()
    logger.info("✓ Task scheduler started")
    try:
        ok, details = await scheduler.run_task_now("memory_reflection")
        if ok:
            logger.info("✓ Scheduler startup sanity run executed: memory_reflection (%s)", details)
        else:
            logger.warning("Scheduler startup sanity run failed: %s", details)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Scheduler startup sanity run errored: %s", exc)

    if config.telegram_enabled and config.telegram_bot_token:
        await bot.start()
    elif not config.telegram_enabled:
        logger.info("Telegram bot disabled via TELEGRAM_ENABLED=false")
    else:
        logger.warning("Telegram bot token is missing; running without Telegram polling")

    logger.info("🎉 HER is fully operational!")
    logger.info("📱 Telegram bot is listening for messages")
    logger.info("👨‍💼 Admin users: %s", admin_user_ids)
    logger.info("⏰ Scheduled tasks: %s", len(scheduler.get_tasks()))

    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await scheduler.stop()
        await bot.stop()
        if api_adapter_server is not None:
            await api_adapter_server.stop()
        if workflow_server is not None:
            await workflow_server.stop()
        if mcp_manager is not None:
            await mcp_manager.stop_all_servers()

    # compatibility with phase-1 smoke checks
    if config.startup_warmup_enabled:
        personality_manager.adjust_trait("demo-user", "warmth", 1)


def _log_degraded_capabilities(snapshot: dict[str, Any]) -> None:
    capabilities = snapshot.get("capabilities", {}) or {}
    for capability_name, payload in capabilities.items():
        available = bool(payload.get("available", False))
        reason = str(payload.get("reason", "unknown"))
        if available:
            logger.info("Capability '%s' available: %s", capability_name, reason)
        else:
            logger.warning("Capability '%s' degraded: %s", capability_name, reason)

    for server_name, state in (snapshot.get("mcp_servers", {}) or {}).items():
        status = str(state.get("status", "unknown"))
        message = str(state.get("message", ""))
        if status == "running":
            logger.info("MCP server '%s' running: %s", server_name, message)
        elif status == "disabled":
            logger.info("MCP server '%s' disabled: %s", server_name, message)
        else:
            logger.warning("MCP server '%s' unavailable (%s): %s", server_name, status, message)


def _publish_runtime_capabilities(config: AppConfig, snapshot: dict[str, Any]) -> None:
    try:
        import redis

        redis_client = redis.Redis(
            host=config.redis_host,
            port=config.redis_port,
            password=config.redis_password,
            decode_responses=True,
        )
        payload = json.dumps(snapshot)
        redis_client.set("her:runtime:capabilities", payload)
        redis_client.lpush("her:runtime:capabilities:history", payload)
        redis_client.ltrim("her:runtime:capabilities:history", 0, 99)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to publish runtime capabilities to Redis: %s", exc)


def _log_runtime_config_selection() -> None:
    selected_agents_path = resolve_config_file("agents.yaml")
    selected_config_dir = selected_agents_path.parent
    runtime_dir = Path("/app/config")
    defaults_dir = Path("/app/config.defaults")
    env_dir = os.getenv("HER_CONFIG_DIR", "").strip()

    logger.info(
        "Runtime config selection: HER_CONFIG_DIR=%s | selected_dir=%s",
        env_dir or "(unset)",
        selected_config_dir,
    )
    if runtime_dir.exists():
        runtime_writable = os.access(runtime_dir, os.W_OK)
        logger.info("Runtime config dir check: path=%s writable=%s", runtime_dir, runtime_writable)
        if not runtime_writable:
            logger.warning(
                "Runtime config volume is read-only for app user; defaults fallback is active (%s). "
                "Set a writable /app/config mount or HER_CONFIG_DIR to a writable path if runtime edits are required.",
                defaults_dir,
            )

    docker_sock = Path("/var/run/docker.sock")
    if docker_sock.exists():
        try:
            sock_stat = docker_sock.stat()
            sock_gid = sock_stat.st_gid
            mode = stat.S_IMODE(sock_stat.st_mode)
            process_groups = os.getgroups()
            running_as_root = os.geteuid() == 0
            in_group = running_as_root or (sock_gid in process_groups)
            logger.info(
                "Docker socket check: gid=%s mode=%s process_groups=%s euid=%s access=%s",
                sock_gid,
                oct(mode),
                process_groups,
                os.geteuid(),
                in_group,
            )
            if not in_group:
                logger.warning(
                    "Current process is not in docker.sock group (%s). Sandbox tools may be degraded. "
                    "Set DOCKER_GID to the host socket group id and restart compose.",
                    sock_gid,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed docker.sock diagnostics: %s", exc)


def main() -> None:
    load_dotenv()
    config = AppConfig()
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    asyncio.run(async_main(config))


if __name__ == "__main__":
    main()

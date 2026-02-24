from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Response

from her.agents.conversation import ConversationAgent
from her.agents.orchestrator import AgentOrchestrator
from her.config.settings import get_settings
from her.guardrails.ethical_core import EthicalCore
from her.interfaces.api.middleware.request_id import RequestIDMiddleware
from her.interfaces.api.routes.chat import router as chat_router
from her.interfaces.api.routes.health import router as health_router
from her.memory.db import MemoryDatabase
from her.memory.store import MemoryStore
from her.memory.working import WorkingMemory
from her.observability.logging import configure_logging, get_logger
from her.observability.metrics import metrics_content_type, metrics_payload
from her.observability.tracing import setup_tracing
from her.personality.drift_engine import DriftEngine
from her.personality.manager import PersonalityManager
from her.personality.vector import (
    load_drift_config,
    load_emotional_baseline,
    load_personality_baseline,
)
from her.providers.anthropic_provider import AnthropicProvider
from her.providers.fallback_router import FallbackRouter
from her.providers.ollama_provider import OllamaProvider
from her.providers.openai_provider import OpenAIProvider


settings = get_settings()
configure_logging(settings.log_level)
setup_tracing(settings.app_name)
logger = get_logger("api_main")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""

    app = FastAPI(title=settings.app_name)
    app.add_middleware(RequestIDMiddleware)

    providers = {
        "openai": OpenAIProvider(settings),
        "anthropic": AnthropicProvider(settings),
        "ollama": OllamaProvider(settings),
    }
    ordered = [providers[name] for name in settings.provider_priority if name in providers]
    router = FallbackRouter(ordered, timeout_seconds=settings.request_timeout_seconds)

    memory_database = MemoryDatabase(settings.database_url)
    memory_store = MemoryStore(memory_database)
    working_memory = WorkingMemory(
        redis_url=settings.redis_url,
        ttl_minutes=settings.working_memory_ttl_minutes,
    )
    baseline_path = Path(__file__).resolve().parents[2] / "config" / "personality_baseline.yaml"
    baseline_personality = load_personality_baseline(baseline_path)
    baseline_emotion = load_emotional_baseline(baseline_path)
    drift_config = load_drift_config(baseline_path)
    personality_manager = PersonalityManager(
        baseline_personality=baseline_personality,
        baseline_emotion=baseline_emotion,
        drift_engine=DriftEngine(baseline_personality, config=drift_config),
        snapshot_store=memory_store,
    )

    conversation_agent = ConversationAgent(
        router=router,
        ethical_core=EthicalCore.default(),
        memory_store=memory_store,
        working_memory=working_memory,
        personality_manager=personality_manager,
    )
    app.state.orchestrator = AgentOrchestrator(conversation_agent)
    app.state.memory_database = memory_database
    app.state.memory_store = memory_store
    app.state.working_memory = working_memory
    app.state.personality_baseline = baseline_personality
    app.state.emotional_baseline = baseline_emotion
    app.state.personality_manager = personality_manager

    app.include_router(health_router)
    app.include_router(chat_router)

    @app.get("/metrics")
    async def metrics() -> Response:
        """Expose Prometheus metrics."""

        return Response(content=metrics_payload(), media_type=metrics_content_type())

    @app.on_event("startup")
    async def startup() -> None:
        healthy = await app.state.memory_database.healthcheck()
        if healthy:
            logger.info("memory_database_ready")
            latest_snapshot = await app.state.memory_store.get_latest_personality_snapshot()
            if latest_snapshot is not None:
                await app.state.personality_manager.restore_from_snapshot(latest_snapshot)
                logger.info("personality_restored_from_snapshot", snapshot_at=str(latest_snapshot.snapshot_at))
        else:
            logger.warning("memory_database_unreachable", database_url=settings.database_url)

    @app.on_event("shutdown")
    async def shutdown() -> None:
        await app.state.working_memory.close()
        await app.state.memory_database.dispose()

    return app


app = create_app()

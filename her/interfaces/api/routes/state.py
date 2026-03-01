from __future__ import annotations

from fastapi import APIRouter, Request

from her.models import StateResponse
from her.observability.metrics import REQUEST_COUNTER

router = APIRouter()


@router.get("/state", response_model=StateResponse)
async def state(request: Request) -> StateResponse:
    """Return current runtime personality/emotion and provider state."""

    REQUEST_COUNTER.labels(route="state").inc()
    settings = request.app.state.settings
    manager = request.app.state.personality_manager
    return StateResponse(
        personality=manager.current_personality,
        emotion=manager.current_emotion,
        provider_priority=list(settings.provider_priority),
        embedding_provider=settings.embedding_provider,
    )

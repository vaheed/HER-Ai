from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Request

from her.models import ChatRequest, ChatResponse
from her.observability.metrics import REQUEST_COUNTER

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    """Handle chat input and return HER response."""

    REQUEST_COUNTER.labels(route="chat").inc()
    orchestrator = request.app.state.orchestrator
    trace_id = cast(str, cast(Any, request.state).request_id)
    llm_response = await orchestrator.handle_interaction(
        session_id=payload.session_id,
        content=payload.content,
        trace_id=trace_id,
    )
    return ChatResponse(
        content=llm_response.content,
        provider=llm_response.provider,
        model=llm_response.model,
        cost_usd=llm_response.cost_usd,
        trace_id=trace_id,
    )

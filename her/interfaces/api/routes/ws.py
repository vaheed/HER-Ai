from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws")
async def websocket_chat(websocket: WebSocket) -> None:
    """Bidirectional websocket chat interface for realtime interactions."""

    await websocket.accept()
    try:
        while True:
            payload = await websocket.receive_json()
            session_id = UUID(str(payload.get("session_id")))
            content = str(payload.get("content", "")).strip()
            if not content:
                await websocket.send_json({"error": "content is required"})
                continue

            trace_id = str(payload.get("trace_id") or "ws-trace")
            llm_response = await websocket.app.state.orchestrator.handle_interaction(
                session_id=session_id,
                content=content,
                trace_id=trace_id,
            )
            await websocket.send_json(
                {
                    "content": llm_response.content,
                    "provider": llm_response.provider,
                    "model": llm_response.model,
                    "cost_usd": llm_response.cost_usd,
                    "trace_id": trace_id,
                }
            )
    except WebSocketDisconnect:
        return

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from aiohttp import WSMsgType, web

logger = logging.getLogger(__name__)

WORKFLOW_NODES: list[dict[str, str]] = [
    {"id": "input", "label": "Input"},
    {"id": "intent_classifier", "label": "Intent Classifier"},
    {"id": "memory_lookup", "label": "Memory Lookup"},
    {"id": "tool_selector", "label": "Tool Selector"},
    {"id": "tool_executor", "label": "Tool Executor"},
    {"id": "llm", "label": "LLM"},
    {"id": "response", "label": "Response"},
]

WORKFLOW_EDGES: list[dict[str, str]] = [
    {"source": "input", "target": "intent_classifier"},
    {"source": "intent_classifier", "target": "memory_lookup"},
    {"source": "memory_lookup", "target": "tool_selector"},
    {"source": "tool_selector", "target": "tool_executor"},
    {"source": "tool_selector", "target": "llm"},
    {"source": "tool_executor", "target": "response"},
    {"source": "llm", "target": "response"},
]


@dataclass
class NodeState:
    node_id: str
    status: str = "idle"
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_ms: float = 0.0
    stdout: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_ms": round(self.duration_ms, 2),
            "stdout": self.stdout[-200:],
        }


@dataclass
class ExecutionState:
    execution_id: str
    user_id: str
    message: str
    started_at: datetime
    nodes: dict[str, NodeState] = field(default_factory=dict)
    events: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=800))
    last_error: str = ""

    def __post_init__(self) -> None:
        if not self.nodes:
            self.nodes = {node["id"]: NodeState(node_id=node["id"]) for node in WORKFLOW_NODES}

    def apply_event(self, event: dict[str, Any]) -> None:
        self.events.append(event)
        node_id = str(event.get("node_id", ""))
        status = str(event.get("status", "idle"))
        event_type = str(event.get("event_type", ""))
        timestamp = _parse_timestamp(event.get("timestamp")) or datetime.now(timezone.utc)

        if node_id not in self.nodes:
            self.nodes[node_id] = NodeState(node_id=node_id)

        node = self.nodes[node_id]
        node.status = status
        if status == "running" and node.started_at is None:
            node.started_at = timestamp
        if status in {"success", "error"}:
            if node.started_at is None:
                node.started_at = timestamp
            node.ended_at = timestamp
            node.duration_ms = max(0.0, (node.ended_at - node.started_at).total_seconds() * 1000.0)

        details = event.get("details") if isinstance(event.get("details"), dict) else {}
        if event_type == "tool_stdout":
            line = str(details.get("line", "")).strip()
            if line:
                node.stdout.append(line)
                if len(node.stdout) > 500:
                    node.stdout = node.stdout[-500:]

        if event_type == "error":
            self.last_error = str(details.get("error", "unknown error"))

    def to_dict(self) -> dict[str, Any]:
        ended_times = [
            node.ended_at for node in self.nodes.values() if node.ended_at is not None
        ]
        terminal_time = max(ended_times) if ended_times else None
        total_latency_ms = (
            max(0.0, (terminal_time - self.started_at).total_seconds() * 1000.0)
            if terminal_time is not None
            else 0.0
        )
        return {
            "execution_id": self.execution_id,
            "user_id": self.user_id,
            "message": self.message,
            "started_at": self.started_at.isoformat(),
            "total_latency_ms": round(total_latency_ms, 2),
            "nodes": {node_id: node.to_dict() for node_id, node in self.nodes.items()},
            "last_error": self.last_error,
            "events": list(self.events),
        }


class WorkflowEventHub:
    """In-memory execution DAG tracker with optional Redis persistence."""

    def __init__(self, max_executions: int = 80) -> None:
        self._executions: dict[str, ExecutionState] = {}
        self._execution_order: deque[str] = deque(maxlen=max_executions)
        self._clients: set[web.WebSocketResponse] = set()
        queue_max_size = max(200, int(os.getenv("HER_WORKFLOW_EVENT_QUEUE_MAX_SIZE", "5000")))
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=queue_max_size)
        self._broadcaster_task: asyncio.Task[Any] | None = None
        self._redis_client = self._build_redis_client()
        self._state_persisted_at: dict[str, float] = {}
        self._state_persist_interval_seconds = max(
            1.0,
            float(os.getenv("HER_WORKFLOW_STATE_PERSIST_INTERVAL_SECONDS", "2.0")),
        )

    @staticmethod
    def _build_redis_client() -> Any:
        try:
            import redis

            return redis.Redis(
                host=os.getenv("REDIS_HOST", "redis"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                password=os.getenv("REDIS_PASSWORD", ""),
                decode_responses=True,
            )
        except Exception:
            return None

    async def start(self) -> None:
        if self._broadcaster_task is None or self._broadcaster_task.done():
            self._broadcaster_task = asyncio.create_task(self._broadcast_loop())

    async def stop(self) -> None:
        if self._broadcaster_task is not None:
            self._broadcaster_task.cancel()
            try:
                await self._broadcaster_task
            except asyncio.CancelledError:
                pass
        for ws in list(self._clients):
            try:
                await ws.close()
            except Exception:
                pass
        self._clients.clear()

    def create_execution(self, user_id: str, message: str) -> str:
        execution_id = uuid4().hex
        state = ExecutionState(
            execution_id=execution_id,
            user_id=str(user_id),
            message=message,
            started_at=datetime.now(timezone.utc),
        )
        self._executions[execution_id] = state
        self._execution_order.appendleft(execution_id)

        while len(self._execution_order) > self._execution_order.maxlen:
            stale = self._execution_order.pop()
            self._executions.pop(stale, None)

        return execution_id

    def emit(
        self,
        *,
        event_type: str,
        execution_id: str,
        node_id: str,
        status: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        if not execution_id:
            return

        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "execution_id": execution_id,
            "node_id": node_id,
            "status": status,
            "details": details or {},
        }

        state = self._executions.get(execution_id)
        if state is None:
            state = ExecutionState(
                execution_id=execution_id,
                user_id="unknown",
                message="",
                started_at=datetime.now(timezone.utc),
            )
            self._executions[execution_id] = state
            self._execution_order.appendleft(execution_id)

        state.apply_event(event)
        self._persist_event(event, state)

        try:
            self._queue.put_nowait(event)
        except Exception:
            logger.debug("Workflow event queue full; dropping event", exc_info=True)

    def snapshot(self, limit: int = 30) -> dict[str, Any]:
        execution_ids = list(self._execution_order)[: max(1, int(limit))]
        executions = [self._executions[eid].to_dict() for eid in execution_ids if eid in self._executions]
        return {
            "nodes": WORKFLOW_NODES,
            "edges": WORKFLOW_EDGES,
            "executions": executions,
        }

    async def register_client(self, ws: web.WebSocketResponse) -> None:
        self._clients.add(ws)
        await ws.send_json({"type": "snapshot", "payload": self.snapshot()})

    def unregister_client(self, ws: web.WebSocketResponse) -> None:
        self._clients.discard(ws)

    async def _broadcast_loop(self) -> None:
        while True:
            event = await self._queue.get()
            payload = {"type": "event", "event": event}
            closed: list[web.WebSocketResponse] = []
            for ws in list(self._clients):
                if ws.closed:
                    closed.append(ws)
                    continue
                try:
                    await ws.send_json(payload)
                except Exception:
                    closed.append(ws)
            for ws in closed:
                self._clients.discard(ws)

    def _persist_event(self, event: dict[str, Any], state: ExecutionState) -> None:
        if self._redis_client is None:
            return
        try:
            serialized = json.dumps(event)
            self._redis_client.lpush("her:workflow:events", serialized)
            self._redis_client.ltrim("her:workflow:events", 0, 1999)
            now_mono = time.monotonic()
            event_type = str(event.get("event_type", ""))
            should_persist_state = event_type in {"response_sent", "error", "llm_completed", "tool_completed"}
            last_persisted = self._state_persisted_at.get(state.execution_id, 0.0)
            if should_persist_state or (now_mono - last_persisted >= self._state_persist_interval_seconds):
                self._redis_client.set(
                    f"her:workflow:execution:{state.execution_id}",
                    json.dumps(state.to_dict()),
                    ex=24 * 3600,
                )
                self._state_persisted_at[state.execution_id] = now_mono
        except Exception:
            logger.debug("Failed to persist workflow event", exc_info=True)


class WorkflowServer:
    """Aiohttp server exposing websocket stream + debug UI."""

    def __init__(self, event_hub: WorkflowEventHub, host: str = "0.0.0.0", port: int = 8081) -> None:
        self._event_hub = event_hub
        self._host = host
        self._port = int(port)
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None

    async def start(self) -> None:
        await self._event_hub.start()

        app = web.Application()
        app.router.add_get("/workflow", self._workflow_page)
        app.router.add_get("/api/workflow/snapshot", self._snapshot)
        app.router.add_get("/ws/workflow", self._ws_workflow)
        app.router.add_get("/workflow/health", self._health)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self._host, self._port)
        await self._site.start()
        logger.info("Workflow server started at http://%s:%s/workflow", self._host, self._port)

    async def stop(self) -> None:
        await self._event_hub.stop()
        if self._site is not None:
            await self._site.stop()
        if self._runner is not None:
            await self._runner.cleanup()

    async def _workflow_page(self, request: web.Request) -> web.Response:
        page_path = Path(__file__).resolve().parent.parent / "workflow_ui" / "index.html"
        if not page_path.exists():
            return web.Response(status=404, text="Workflow UI not found")
        return web.FileResponse(path=page_path)

    async def _snapshot(self, request: web.Request) -> web.Response:
        return web.json_response(self._event_hub.snapshot())

    async def _health(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def _ws_workflow(self, request: web.Request) -> web.StreamResponse:
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        await self._event_hub.register_client(ws)

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    if msg.data == "ping":
                        await ws.send_str("pong")
                elif msg.type == WSMsgType.ERROR:
                    break
        finally:
            self._event_hub.unregister_client(ws)

        return ws


def _parse_timestamp(raw: Any) -> datetime | None:
    if raw is None:
        return None
    try:
        value = str(raw)
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except Exception:
        return None

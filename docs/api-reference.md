# API Reference

Base URL: `http://127.0.0.1:8000`

## REST Endpoints

### `GET /health`

Returns health heartbeat.

### `POST /chat`

Request:
```json
{
  "session_id": "<uuid>",
  "content": "Hello HER"
}
```

Response:
```json
{
  "content": "...",
  "provider": "openai|anthropic|custom|ollama|cache",
  "model": "...",
  "cost_usd": 0.0,
  "trace_id": "..."
}
```

### `GET /memory/search?q=<text>&top_k=<int>`

Searches semantic memory using embedding similarity.

### `GET /state`

Returns runtime state including personality vector, emotional state, provider order, and embedding provider.

### `GET /goals?limit=<int>`

Returns active goals sorted by priority.

### `GET /metrics`

Prometheus-compatible metrics payload.

## WebSocket

### `WS /ws`

Request payload:
```json
{
  "session_id": "<uuid>",
  "content": "Hello",
  "trace_id": "optional"
}
```

Response payload:
```json
{
  "content": "...",
  "provider": "...",
  "model": "...",
  "cost_usd": 0.0,
  "trace_id": "..."
}
```

## Telegram Bot Commands

- `/reflect`: trigger reflection cycle and return compact personality update
- `/goals`: list active goals
- `/mood`: return current emotional + personality summary

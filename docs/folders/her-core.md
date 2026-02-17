# Folder Reference: her-core

## Purpose

Main runtime package for HER-Ai.

## Structure

- `her-core/main.py` - async bootstrap, memory init, MCP init, scheduler start, Telegram startup
- `her-core/config.py` - environment-backed app config dataclass
- `her-core/agents/` - CrewAI agent definitions and crew orchestration
- `her-core/her_telegram/` - bot wiring, commands, message handlers, autonomous operator
- `her-core/her_mcp/` - MCP manager and tool wrappers (including sandbox and optional twitter)
- `her-core/memory/` - Mem0 integration, Redis context store, DB init/schema
- `her-core/utils/` - LLM factory, scheduler, retry, metrics, decision log, reinforcement logic
- `her-core/docker-entrypoint.sh` - runtime config seeding/fallback behavior

## How It Works

`main.py` wires memory + tools + agents + scheduler + Telegram handlers, publishes capability snapshots, then runs indefinitely.

## How to Test

```bash
pytest tests/test_smoke.py -q
pytest tests/test_runtime_guards.py -q
```

Runtime verification:
```bash
docker compose logs --tail=200 her-bot
```

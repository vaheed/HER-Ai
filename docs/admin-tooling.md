# Admin and Tooling Guide

## Dashboard Operations

Dashboard entrypoint: `dashboard/app.py`.

Pages and operational purpose:
- Overview: KPIs, capability diagnostics, memory/system summaries
- Logs: runtime logs and MCP diagnostics
- Recent Chats: latest interaction traces
- Executors: sandbox execution history
- Jobs: scheduler state and history
- Decisions: decision log audit trail
- Metrics: message/token trends
- Memory: memory growth/search and category insights
- System Health: Redis/Postgres/runtime capability snapshot

Access URL: `http://localhost:8501`.

## Telegram Admin Commands

Handlers are implemented in `her-core/her_telegram/handlers.py`.

Core commands:
- `/status`
- `/mcp`
- `/memories`
- `/personality`
- `/schedule`
- `/example`

## Scheduler Tooling

Scheduler engine: `her-core/utils/scheduler.py`.

Useful admin operations:
```text
/schedule list
/schedule set <task> <interval>
/schedule enable <task>
/schedule disable <task>
/schedule run <task>
/schedule add <name> <type> <interval> [key=value ...]
```

Persistence behavior:
- primary: `config/scheduler.yaml`
- fallback (if config path read-only): Redis key `her:scheduler:tasks_override`

## MCP and Sandbox Tooling

- MCP startup/status: `her-core/her_mcp/manager.py`
- Curated tool integration: `her-core/her_mcp/tools.py`
- Sandbox command/network/security helpers: `her-core/her_mcp/sandbox_tools.py`

Runtime checks:
- `/mcp` command
- dashboard capability panels
- `docker compose logs her-bot`

## Operational CLI Commands

```bash
docker compose ps
docker compose logs -f her-bot
docker compose logs -f dashboard
docker compose exec sandbox check_pentest_tools
```

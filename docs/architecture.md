# Architecture Overview

## System Layers

HER-Ai is organized into five layers:

1. Interface layer
- Telegram bot interface (`her-core/her_telegram/bot.py`, `her-core/her_telegram/handlers.py`)
- Admin dashboard (`dashboard/app.py`)

2. Orchestration layer
- Runtime composition and service boot (`her-core/main.py`)
- CrewAI agents (`her-core/agents/*.py`)
- Task scheduler (`her-core/utils/scheduler.py`)

3. Intelligence and tools layer
- LLM provider factory (`her-core/utils/llm_factory.py`)
- MCP server manager (`her-core/her_mcp/manager.py`)
- Curated tool wrappers (`her-core/her_mcp/tools.py`)
- Sandbox execution adapters (`her-core/her_mcp/sandbox_tools.py`)

4. Memory and state layer
- Long-term memory wrapper (`her-core/memory/mem0_client.py`)
- Short-term context cache (`her-core/memory/redis_client.py`)
- DB initialization and schema (`her-core/memory/db_init.py`, `her-core/memory/schemas.sql`)
- Runtime metrics/decision logs (`her-core/utils/metrics.py`, `her-core/utils/decision_log.py`)

5. Infrastructure layer
- Compose stack (`docker-compose.yml`)
- Image definitions (`her-core/Dockerfile`, `dashboard/Dockerfile`, `sandbox/Dockerfile`)
- CI/CD (`.github/workflows/ci.yml`)

## Runtime Flow

```text
Telegram message
  -> her_telegram.handlers.MessageHandlers
  -> context update (Redis)
  -> memory lookup (Mem0/pgvector)
  -> LLM response generation (with optional failover)
  -> optional tool/sandbox actions
  -> metrics + decision logs persisted
```

## Major Modules and Responsibilities

| Module | Responsibility | Primary Files |
|---|---|---|
| `her-core` | Main assistant runtime, agents, memory, telegram handling, scheduling | `her-core/main.py`, `her-core/her_telegram/handlers.py` |
| `her-core/agents` | CrewAI roles for conversation, reflection, personality, tools | `her-core/agents/conversation_agent.py`, `her-core/agents/crew_orchestrator.py` |
| `her-core/her_mcp` | MCP server lifecycle, tool abstraction, sandbox utilities | `her-core/her_mcp/manager.py`, `her-core/her_mcp/tools.py` |
| `her-core/memory` | Mem0 integration, context cache, schema compatibility | `her-core/memory/mem0_client.py`, `her-core/memory/schemas.sql` |
| `dashboard` | Operational visibility, health and metrics UI | `dashboard/app.py` |
| `tests` | Runtime guardrails and smoke checks | `tests/test_runtime_guards.py`, `tests/test_smoke.py` |

## Service Topology (Compose)

| Service | Purpose | Data |
|---|---|---|
| `her-bot` | Core app runtime | Redis + PostgreSQL + MCP/sandbox access |
| `postgres` | Long-term memory and logs | persistent volume |
| `redis` | context and metrics cache | persistent AOF volume |
| `ollama` + `ollama-init` | local model serving and model pre-pull | model volume |
| `sandbox` | isolated execution tools | ephemeral workspace volume |
| `dashboard` | monitoring and operations UI | reads Redis/Postgres |

Reference: `docker-compose.yml`.

## Design Notes

- Config resolution supports runtime volume and fallback defaults via `HER_CONFIG_DIR` (`her-core/utils/config_paths.py`).
- MCP startup is resilient to per-server failures/timeouts (`MCP_SERVER_START_TIMEOUT_SECONDS`).
- Memory reads/writes can degrade gracefully when backend is unavailable if `MEMORY_STRICT_MODE=false`.
- Scheduler tasks persist to YAML and fallback to Redis override if config path is not writable.

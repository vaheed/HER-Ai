# HER-Ai

HER-Ai is a containerized personal AI assistant platform inspired by the long-memory companion model from *HER*.
It combines Telegram interaction, multi-agent orchestration, persistent memory, sandboxed execution, and an operational dashboard.

## Project Vision

HER-Ai is built to support a long-lived assistant that can:
- maintain continuity across conversations,
- adapt communication style over time,
- run safe tool-assisted tasks,
- stay observable and operable in production-like environments.

## Architecture

The system is split into runtime, interfaces, data, and operations layers.

```text
User (Telegram) / Operator (Dashboard)
        |
        v
her-core runtime
  - Telegram handlers and bot loop
  - CrewAI agents (conversation/reflection/personality/tool)
  - MCP + sandbox tooling
        |
        v
Memory and state
  - Redis (short-term context and runtime metrics)
  - PostgreSQL + pgvector + Mem0 (long-term memory)
        |
        v
Operations
  - Docker Compose orchestration
  - CI pipeline + container publishing + docs deployment
```

Key code entry points:
- Runtime bootstrap: `her-core/main.py`
- Telegram command/message handling: `her-core/her_telegram/handlers.py`
- MCP lifecycle: `her-core/her_mcp/manager.py`
- Scheduler engine: `her-core/utils/scheduler.py`
- Dashboard app: `dashboard/app.py`
- Compose stack: `docker-compose.yml`

Full architecture doc: `docs/architecture.md`.

## Supported Platforms and Requirements

| Item | Requirement |
|---|---|
| OS | macOS, Linux, Windows (WSL2 recommended for local Linux-like workflow) |
| Container runtime | Docker Engine 24+ or Docker Desktop 4+ |
| Docker Compose | v2 (`docker compose`) |
| CPU/RAM | Minimum 4 CPU / 8 GB RAM (more for local Ollama models) |
| Network | Required for model/tool APIs and package pulls |

Optional local (non-Docker) development:
- Python 3.11
- Node.js + npm (for MCP server binaries)
- PostgreSQL 17 + pgvector
- Redis 7

## Installation

### 1. Clone

```bash
git clone https://github.com/vaheed/HER-Ai.git
cd HER-Ai
```

### 2. Configure environment

```bash
cp .env.example .env
```

Set at minimum:
- `TELEGRAM_BOT_TOKEN`
- `ADMIN_USER_ID`
- your chosen LLM credentials/provider settings

### 3. Start stack

```bash
docker compose up -d --build
```

### 4. Verify services

```bash
docker compose ps
curl -sS http://localhost:8000
```

Expected health response:

```json
{"status":"ok"}
```

Detailed platform setup: `docs/installation.md`.

## Usage

### Basic usage

1. Open your bot in Telegram.
2. Send `/start`.
3. Send normal messages.

Basic commands:
- `/help`
- `/example`
- `/status` (admin)
- `/schedule list` (admin)

### Advanced usage

Natural-language scheduling:
- `Remind me in 20 minutes to call Sara.`
- `Every day at 9am remind me to review priorities.`

Automation workflow intent:
- `Check BTC every 5 minutes and alert me if it drops 5%.`

Tooling/security diagnostics intent:
- `Check SSL expiry for github.com.`
- `Run a DNS lookup for openai.com.`

Complete usage guide: `docs/usage.md`.

## Configuration Reference

Configuration sources:
- Environment variables: `.env.example`
- YAML runtime config: `config/*.yaml`

Primary runtime controls include:
- LLM routing and failover (`LLM_PROVIDER`, `LLM_ENABLE_FALLBACK`)
- memory strictness (`MEMORY_STRICT_MODE`)
- Telegram mode/rate-limits (`TELEGRAM_PUBLIC_*`)
- scheduler/sandbox limits (`HER_AUTONOMOUS_MAX_STEPS`, `HER_SANDBOX_*`)
- MCP profile selection (`MCP_CONFIG_PATH`)

Full variable-by-variable reference: `docs/configuration.md`.

If Ollama memory operations fail with an error like `model requires more system memory than is available`, use a smaller model or increase container memory.

## Testing

Run repository tests:

```bash
pytest -q
```

Run targeted tests:

```bash
pytest tests/test_smoke.py -q
pytest tests/test_runtime_guards.py -q
```

Run runtime validation with containers:

```bash
docker compose logs --tail=200 her-bot
```

Testing guide: `docs/testing.md`.

## Build and Deployment

### Local build

```bash
docker compose build her-bot dashboard sandbox
```

### Start in detached mode

```bash
docker compose up -d
```

### Production guidance
- prefer pinned image tags over `latest`,
- externalize secrets,
- mount writable config only where required,
- monitor dashboard + logs + health checks.

Deployment details: `docs/deployment.md`.

## Documentation Map

- Docs home: `docs/index.md`
- Architecture: `docs/architecture.md`
- Installation: `docs/installation.md`
- Configuration: `docs/configuration.md`
- Usage: `docs/usage.md`
- Testing: `docs/testing.md`
- Deployment: `docs/deployment.md`
- Admin and tooling: `docs/admin-tooling.md`
- Prompt library: `docs/examples.md`
- Developer workflow: `docs/developer-guidelines.md`
- Roadmap: `docs/roadmap.md`

## Contribution Guidelines

1. Read `AGENTS.md` and `docs/index.md` before changes.
2. Keep cross-component changes synchronized (`her-core`, `dashboard`, `config`, `docs`, compose/CI).
3. Update docs when behavior/configuration changes.
4. Run relevant tests before opening PR.
5. Include summary, tests run, and follow-ups in PR description.

See `docs/developer-guidelines.md` for coding standards, git workflow, and release process.

## License

MIT (see repository license metadata).

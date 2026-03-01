# HER AI

HER is a production-oriented, local-first AI companion platform with persistent memory, dynamic personality, emotional modulation, provider fallback routing, and multiple interfaces (REST, WebSocket, Telegram).

Repository: https://github.com/vaheed/her-ai
Contact: me@vaheed.net

## Status

Phase 0, Phase 1, Phase 2, and Phase 3 are implemented and validated with automated tests.

Current implementation includes:
- Async Python architecture (FastAPI + async SQLAlchemy + Redis)
- Multi-provider LLM routing (`openai -> anthropic -> custom -> ollama -> cache`)
- Embedding providers (`ollama` default, optional `custom`)
- PostgreSQL + pgvector memory schema via Alembic
- Personality drift engine + emotional overlay + prompt builder
- Conversation pipeline with preprocessing, retrieval, token budgeting, and event emission
- REST + WebSocket APIs and Telegram bot command handlers
- Unit, integration, and simulation test suites

## Documentation

- [Documentation Index](docs/README.md)
- [Architecture](docs/architecture.md)
- [API Reference](docs/api-reference.md)
- [Deployment Guide](docs/deployment.md)
- [Testing and Quality](docs/testing-and-quality.md)
- [Operations Runbook](docs/operations-runbook.md)
- [Release Readiness](docs/release-readiness.md)
- [Roadmap and Phase Status](docs/roadmap.md)

## Quickstart (Local)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
pytest -q
python main.py
```

Server defaults to `http://127.0.0.1:8000`.

## Docker

Single stack (dev/prod-ready via `.env` values):

```bash
cp .env.example .env
docker-compose up --build -d
```

Compose includes:
- PostgreSQL 16 + pgvector
- Redis 7
- Ollama service
- `ollama-init` bootstrap job that pulls chat + embedding models before app starts

## Runtime Interfaces

REST API:
- `POST /chat`
- `GET /memory/search?q=...`
- `GET /state`
- `GET /goals`
- `GET /health`
- `GET /metrics`

WebSocket:
- `WS /ws` JSON request/response loop

Telegram bot:

```bash
python scripts/run_telegram_bot.py
```

Supported commands:
- `/reflect`
- `/goals`
- `/mood`

## Environment Configuration

Use [`.env.example`](.env.example) as the template.

Highlights:
- `PROVIDER_PRIORITY` controls LLM fallback order
- `EMBEDDING_PROVIDER` controls embedding backend (`ollama|custom|none`)
- `CONVERSATION_TOKEN_BUDGET`, `SEMANTIC_TOP_K`, `RECENT_EPISODE_LIMIT`, `ACTIVE_GOAL_LIMIT` tune the Phase 3 pipeline

## Quality Gates

```bash
python3 -m ruff check .
python3 -m mypy her
pytest -q
```

Optional pre-commit:

```bash
pre-commit install
pre-commit run --all-files
```

## Production Notes

- Keep secrets out of git and use an external secrets manager in production.
- Run Alembic migrations before each deploy (`alembic upgrade head`).
- Pin model versions for reproducible behavior.
- Keep backup/restore policies for PostgreSQL and monitoring/alerting enabled.

## Contributing and License

- Contributing guide: [CONTRIBUTING.md](CONTRIBUTING.md)
- License: [MIT](LICENSE)

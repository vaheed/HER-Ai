# HER AI

Base implementation for HER, a local-first AI companion platform.

## What is included

- Async Python package scaffold matching the HER architecture
- FastAPI service (`/health`, `/chat`, `/metrics`)
- Provider abstraction with fallback routing: OpenAI -> Anthropic -> Ollama -> cache
- Structured logging (`structlog`), Prometheus metrics, OpenTelemetry tracing setup
- Personality vector, emotional overlay, drift engine
- Phase 1 memory engine: SQLAlchemy async store, Alembic migrations, pgvector schema, Redis working memory
- Guardrails and sandboxed tool runner
- Docker and Docker Compose for local infrastructure
- Unit tests for drift, guardrails, fallback, settings, and working-memory fallback

## Quickstart

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

## Run with Docker Compose

```bash
docker compose -f docker/docker-compose.yml up --build
```

## Notes

- If no provider keys are set, router will try Ollama (`OLLAMA_BASE_URL`) and then cached response fallback.
- Run schema migrations any time with `alembic upgrade head`.
- Run daily aging pipeline with `python scripts/run_memory_aging.py`.
- For a local smoke test of the provider pipeline, run:

```bash
python scripts/hello_her.py
```

# HER AI

Base implementation for HER, a local-first AI companion platform.

## What is included

- Async Python package scaffold matching the HER architecture
- FastAPI service (`/health`, `/chat`, `/metrics`)
- Provider abstraction with fallback routing: OpenAI -> Anthropic -> Custom Endpoint -> Ollama -> cache
- Embedding providers with pluggable interface (default: Ollama embeddings)
- Structured logging (`structlog`), Prometheus metrics, OpenTelemetry tracing setup
- Phase 2 personality system: dynamic drift manager, emotional transition/decay, tone overlay, dynamic prompt builder
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

The compose stack includes `ollama` and an `ollama-init` bootstrap service that pulls both chat and embedding models before the app starts.

## Notes

- If no provider keys are set, router will try Ollama (`OLLAMA_BASE_URL`) and then cached response fallback.
- Configure custom LLM endpoint with `CUSTOM_LLM_ENDPOINT` and `CUSTOM_LLM_MODEL`.
- Configure embedding backend with `EMBEDDING_PROVIDER` (`ollama`, `custom`, or `none`).
- Run schema migrations any time with `alembic upgrade head`.
- Run daily aging pipeline with `python scripts/run_memory_aging.py`.
- For a local smoke test of the provider pipeline, run:

```bash
python scripts/hello_her.py
```

## Pre-commit

```bash
pre-commit install
pre-commit run --all-files
```

# Testing and Quality

## Quality Gates

Run locally before push:

```bash
python3 -m ruff check .
python3 -m mypy her
pytest -q
```

## Test Layers

- Unit tests (`tests/unit`)
  - drift/emotion/personality behavior
  - provider fallback behavior
  - API route behavior
  - token budget and preprocessing logic
  - telegram command handler behavior
- Integration tests (`tests/integration`)
  - persistent memory with live PostgreSQL + Redis
- Simulation tests (`tests/simulation`)
  - end-to-end conversation pipeline behavior with retrieval/context/events

## Real Test Workflow

1. Start dependencies (`postgres`, `redis`, optional `ollama`).
2. Apply migrations: `alembic upgrade head`.
3. Run test suite: `pytest -q`.
4. Smoke check endpoints:
   - `GET /health`
   - `POST /chat`
   - `GET /state`
   - `GET /memory/search`
   - `GET /goals`

## Pre-commit

```bash
pre-commit install
pre-commit run --all-files
```

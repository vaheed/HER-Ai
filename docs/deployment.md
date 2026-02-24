# Deployment Guide

## Prerequisites

- Python 3.12 recommended
- Docker + Docker Compose
- PostgreSQL and Redis connectivity
- Optional cloud/API provider credentials

## Environment Setup

1. Copy template:
   ```bash
   cp .env.example .env
   ```
2. Set secrets and endpoints.
3. Verify provider order and embedding provider.

## Local Process Deployment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
python main.py
```

## Docker Compose Deployment

Development:
```bash
docker compose -f docker/docker-compose.yml up --build
```

Production-like:
```bash
docker compose -f docker/docker-compose.prod.yml up --build -d
```

Notes:
- `ollama-init` blocks app startup until chat and embedding models are pulled.
- App service runs migrations at startup before launching API.

## GitHub CI/CD

- `test.yml`:
  - lint, typecheck, migrations, full tests
  - uses live Postgres and Redis services in workflow
- `deploy.yml`:
  - builds and pushes container image to GHCR

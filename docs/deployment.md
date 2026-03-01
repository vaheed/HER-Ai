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

Single compose stack:
```bash
cp .env.example .env
docker-compose up --build -d
```

Notes:
- `ollama-init` blocks app startup until chat and embedding models are pulled.
- App service runs migrations at startup before launching API.

## GitHub CI/CD

- `test.yml` (`ci-cd` workflow):
  - lint, typecheck, migrations, full tests
  - then builds and pushes container image to GHCR (after tests pass)

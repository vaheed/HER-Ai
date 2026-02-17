# Installation and Setup Guide

## Prerequisites

- Docker Engine or Docker Desktop with Compose v2
- Git
- Internet access for dependency pulls
- Telegram Bot Token

Recommended host resources:
- 4+ CPU cores
- 8+ GB RAM (increase for larger local models)

## Universal Setup (All Platforms)

1. Clone repository
```bash
git clone https://github.com/vaheed/HER-Ai.git
cd HER-Ai
```

2. Create environment file
```bash
cp .env.example .env
```

3. Set required variables in `.env`
- `TELEGRAM_BOT_TOKEN`
- `ADMIN_USER_ID`
- LLM provider values (`LLM_PROVIDER` and matching API/model vars)

4. Start stack
```bash
docker compose up -d --build
```

5. Validate startup
```bash
docker compose ps
curl -sS http://localhost:8000
```

## Platform-Specific Notes

## macOS

- Use Docker Desktop.
- Increase memory allocation in Docker Desktop settings if Ollama model load fails.
- Access dashboard: `http://localhost:8501`.

## Linux

- Install Docker Engine + Compose plugin.
- Ensure current user can run Docker (docker group) or run commands via sudo.
- If running rootless Docker, validate socket mapping behavior for sandbox access.

## Windows

- Recommended: Docker Desktop + WSL2 backend.
- Run commands in WSL terminal for path consistency.
- Ensure port mappings `8000`, `8501`, `11434` are available.

## Optional Local (No Docker) Setup

Not the primary path, but useful for debugging:
- Python 3.11 virtualenv
- local PostgreSQL + pgvector
- local Redis
- Node.js/npm for MCP dependencies

Install runtime deps:
```bash
pip install -r her-core/requirements.txt
```

Run tests:
```bash
pytest -q
```

## First-Run Checks

- Bot service logs: `docker compose logs --tail=200 her-bot`
- Dashboard logs: `docker compose logs --tail=200 dashboard`
- Sandbox tool check: `docker compose exec sandbox check_pentest_tools`

## Troubleshooting Quick List

- `her-bot` not healthy: check env vars and Postgres/Redis health in `docker compose ps`.
- MCP servers unavailable: check `MCP_CONFIG_PATH` and required env placeholders.
- Memory failures with Ollama: reduce model size or increase memory; use fallback behavior (`MEMORY_STRICT_MODE=false`).

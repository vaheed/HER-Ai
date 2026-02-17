# Deployment Guide

## Deployment Modes

- Local/staging with `docker compose`
- Production-like deployment with prebuilt images from GHCR

## Container Build and Run

Build images:

```bash
docker compose build her-bot dashboard sandbox
```

Run services:

```bash
docker compose up -d
```

Validate:

```bash
docker compose ps
curl -sS http://localhost:8000
```

## Production Recommendations

1. Use immutable image tags (release tags) instead of `latest`.
2. Store secrets in external secret manager or protected env system.
3. Restrict network exposure to required ports.
4. Enable log collection and retention for `her-bot` and `dashboard`.
5. Backup Postgres and Redis volumes.
6. Track MCP availability and scheduler task health in dashboard pages.

## Environment Hardening

- Set strong DB/Redis credentials.
- Review `MCP_CONFIG_PATH` and disable unneeded servers.
- Keep sandbox limits (`HER_SANDBOX_*`) conservative in shared environments.
- Run with explicit timezone (`TZ`) and operational alerts.

## CI/CD and Image Publishing

` .github/workflows/ci.yml` builds and publishes:
- `ghcr.io/<owner>/her-ai/her-bot`
- `ghcr.io/<owner>/her-ai/her-dashboard`
- `ghcr.io/<owner>/her-ai/her-sandbox`

Docs are built with MkDocs and deployed to GitHub Pages when `main` updates.

## Operational Runbook (Minimal)

1. Pull latest stable images.
2. Update `.env` and config files.
3. Start services with compose.
4. Confirm health endpoint and dashboard.
5. Test `/status` and `/mcp` in Telegram.
6. Review logs for startup capability warnings.

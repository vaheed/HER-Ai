# Folder Reference: init-scripts

## Purpose

Database initialization SQL for PostgreSQL container startup.

## Files

- `init-scripts/init-db.sql`

## What It Sets Up

- required extensions (`vector`, `pgcrypto`)
- users/personality/conversation/decision/reinforcement tables
- compatibility migration logic for legacy `memories` table shapes

## Validation

Start DB and inspect logs:

```bash
docker compose up -d postgres
docker compose logs --tail=100 postgres
```

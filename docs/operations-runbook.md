# Operations Runbook

## Daily Operations

- Check `/health` and `/metrics`
- Review structured logs for provider errors and fallback frequency
- Monitor Redis and PostgreSQL health

## Scheduled Jobs

Run aging and reflection jobs:

```bash
python scripts/run_memory_aging.py
python scripts/run_reflection.py
```

## Incident Patterns

### Provider failures

Symptoms:
- fallback warnings in logs
- increased `provider_cache_fallback` events

Actions:
- verify provider credentials
- verify network egress
- reorder `PROVIDER_PRIORITY` as temporary mitigation

### Embedding failures

Symptoms:
- empty semantic memory search results
- warning logs from `embedding_service`

Actions:
- verify `EMBEDDING_PROVIDER`
- verify `OLLAMA_EMBEDDING_MODEL` pull status or custom endpoint availability

### Database unavailable

Symptoms:
- startup warning `memory_database_unreachable`

Actions:
- verify DSN and connectivity
- verify migrations applied
- restore from backup if required

## Backup and Recovery

- PostgreSQL:
  - schedule logical backups
  - test restore in staging
- Redis:
  - persistence strategy based on workload criticality
- Keep Alembic revision history immutable

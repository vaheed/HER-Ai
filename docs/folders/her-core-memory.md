# Code Area: her-core/memory

## Purpose

Implements long-term memory integration (Mem0 + pgvector) and short-term conversation context storage (Redis).

## Files

- `her-core/memory/mem0_client.py` - memory add/search/update/delete wrapper
- `her-core/memory/redis_client.py` - context cache API
- `her-core/memory/db_init.py` - schema initialization helper
- `her-core/memory/schemas.sql` - database schema and compatibility migrations
- `her-core/memory/fallback_memory.py` - degraded-mode in-process memory behavior

## How to Test

```bash
pytest tests/test_runtime_guards.py -q
```

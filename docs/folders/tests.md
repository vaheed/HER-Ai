# Folder Reference: tests

## Purpose

Regression and runtime guard tests for critical behavior.

## Files

- `tests/test_smoke.py` - baseline config and structural checks
- `tests/test_runtime_guards.py` - guardrails around Telegram, scheduler, MCP, memory, fallback behavior

## Execution

```bash
pytest -q
```

## Notes

Tests intentionally include source-level assertions to prevent silent removal of critical safety and reliability paths.

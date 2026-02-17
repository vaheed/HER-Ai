# Testing Guide

## Test Scope

Current tests focus on:
- configuration and runtime guardrails,
- regression checks for critical integration behavior,
- smoke assertions for project shape and startup logic.

Primary files:
- `tests/test_smoke.py`
- `tests/test_runtime_guards.py`

## Running Tests

From repository root:

```bash
pytest -q
```

Targeted:

```bash
pytest tests/test_smoke.py -q
pytest tests/test_runtime_guards.py -q
```

## Runtime Validation (Container Stack)

```bash
docker compose up -d --build
docker compose ps
curl -sS http://localhost:8000
docker compose logs --tail=200 her-bot
```

Sandbox diagnostics:

```bash
docker compose exec sandbox check_pentest_tools
```

## How Tests Are Structured

- Static file assertions verify expected command registrations and safeguards.
- Config assertions ensure required sections stay present.
- Runtime behavior guarantees are encoded as source-level checks to prevent accidental removals.

## Writing New Tests

1. Add tests under `tests/` using `pytest` style.
2. Prefer behavior-oriented assertions over implementation noise.
3. For config and docs impacting behavior, add guard tests that protect critical expectations.
4. Run full suite before PR.

## CI Integration

GitHub Actions workflow (`.github/workflows/ci.yml`) runs:
1. Python setup
2. dependencies install
3. `pytest -q`
4. build/push container images (non-PR push paths)
5. docs build/deploy from `main`

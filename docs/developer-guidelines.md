# Developer Guidelines

## Engineering Standards

- Keep behavioral changes aligned across runtime, dashboard, config, tests, and docs.
- Prefer small, reviewable commits.
- Add tests for behavior changes.
- Keep `.env.example` synchronized when adding env variables.

## Code Quality

- Python style: clear naming, modular functions, explicit error handling.
- Avoid hidden side effects in handlers/scheduler flows.
- Keep backward compatibility for config resolution and startup behavior where practical.

## Linting and Formatting

This repository currently enforces tests in CI. If you add local lint tooling, document commands and keep CI aligned.

Minimum pre-PR checks:
```bash
pytest -q
```

## Git Workflow

1. Create branch from `main`.
2. Implement code + tests + docs together.
3. Re-run tests.
4. Open PR with change summary and test evidence.

Recommended PR template sections:
- Scope
- Behavior changes
- Config/docs changes
- Tests run
- Risks/rollback notes

## Release Process

CI workflow (`.github/workflows/ci.yml`) handles:
1. test job
2. image build/publish to GHCR
3. docs build/deploy (main branch)

For tagged releases:
- push semantic tag (`vX.Y.Z`)
- verify GHCR images and docs deployment
- publish release notes with migration/config notes

## Documentation Rules

- Update `README.md` for top-level behavior/config/runtime changes.
- Update relevant files under `docs/` for module-level changes.
- Keep cross-references to source files accurate.

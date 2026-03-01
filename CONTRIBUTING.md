# Contributing

Thanks for contributing to HER AI.

Repository: https://github.com/vaheed/her-ai
Maintainer contact: me@vaheed.net

## Development Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
```

Optional local infra:

```bash
docker-compose up --build
```

## Branch and PR Workflow

1. Create a feature branch from `main`.
2. Keep changes scoped and atomic.
3. Add or update tests with code changes.
4. Run all quality checks before opening a PR.
5. Open PR with clear summary, risk notes, and test evidence.

## Required Quality Checks

```bash
python3 -m ruff check .
python3 -m mypy her
pytest -q
```

## Commit Guidance

- Use clear, imperative commit messages.
- Reference the area changed (for example: `memory`, `providers`, `interfaces`, `docs`).
- Avoid bundling unrelated refactors in feature commits.

## Coding Expectations

- Async for I/O paths.
- Full type annotations.
- No secrets in source control.
- Keep guardrails intact.
- Keep migrations backward-aware.

## Documentation

If behavior changes, update at least one relevant document in `docs/` and the root `README.md` when needed.

## Security

Do not disclose vulnerabilities publicly. Send responsible disclosures to: me@vaheed.net.

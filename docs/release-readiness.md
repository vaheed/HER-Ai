# Release Readiness

This checklist is used before pushing to GitHub and releasing.

## Phase Coverage

- [x] Phase 0 implemented
- [x] Phase 1 implemented
- [x] Phase 2 implemented
- [x] Phase 3 implemented

## Engineering Readiness

- [x] Lint clean (`ruff`)
- [x] Typecheck clean (`mypy`)
- [x] Unit tests passing
- [x] Integration tests present (Postgres + Redis)
- [x] Simulation tests present (conversation pipeline)
- [x] Docker compose stacks for dev and prod-like
- [x] Alembic migration flow present
- [x] `.env.example` documented with best-practice comments
- [x] CI workflow for tests
- [x] Deploy workflow for image build/push

## Governance Readiness

- [x] MIT license file present
- [x] Contributing guide present
- [x] README comprehensive and linked to docs

## Repository Metadata

- Repository: https://github.com/vaheed/her-ai
- Maintainer contact: me@vaheed.net

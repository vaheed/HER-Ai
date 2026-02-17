# Documentation Index

This is the central documentation map for HER-Ai.
Use this page to navigate architecture, setup, operations, development workflow, and module-level references.

## Structured TOC

- 1. Project Foundations
  - `README.md` - project overview, quick start, contribution entry points
  - `docs/architecture.md` - runtime architecture, data flow, module responsibilities
  - `docs/roadmap.md` - 3-phase future implementation roadmap
- 2. Setup and Runtime
  - `docs/installation.md` - platform-by-platform installation and first boot
  - `docs/configuration.md` - full environment and YAML configuration reference
  - `docs/usage.md` - user/admin workflows and command usage
  - `docs/deployment.md` - container deployment and production guidance
- 3. Quality and Operations
  - `docs/testing.md` - test strategy and test authoring guidance
  - `docs/admin-tooling.md` - dashboard pages, CLI operations, script workflows
- 4. Examples and Team Workflow
  - `docs/examples.md` - prompt library and scenario walkthroughs
  - `docs/developer-guidelines.md` - coding standards, linting, git, release flow
- 5. Folder and Code-Area Reference
  - `docs/folders/her-core.md`
  - `docs/folders/her-core-agents.md`
  - `docs/folders/her-core-telegram.md`
  - `docs/folders/her-core-memory.md`
  - `docs/folders/her-core-mcp.md`
  - `docs/folders/her-core-utils.md`
  - `docs/folders/dashboard.md`
  - `docs/folders/config.md`
  - `docs/folders/sandbox.md`
  - `docs/folders/tests.md`
  - `docs/folders/init-scripts.md`
  - `docs/folders/github-workflows.md`
  - `docs/folders/docs.md`

## Recommended Reading Paths

- New contributor: `README.md` -> `docs/installation.md` -> `docs/usage.md` -> `docs/developer-guidelines.md`
- Operator/admin: `docs/installation.md` -> `docs/configuration.md` -> `docs/admin-tooling.md` -> `docs/deployment.md`
- Feature developer: `docs/architecture.md` -> `docs/folders/her-core.md` -> `docs/testing.md` -> `docs/developer-guidelines.md`

## Cross-Reference Entry Points

- Runtime bootstrap: `her-core/main.py`
- Telegram handler logic: `her-core/her_telegram/handlers.py`
- MCP integration: `her-core/her_mcp/manager.py`
- Scheduler and task persistence: `her-core/utils/scheduler.py`
- Dashboard UI and data readers: `dashboard/app.py`
- Container orchestration: `docker-compose.yml`
- CI workflow: `.github/workflows/ci.yml`

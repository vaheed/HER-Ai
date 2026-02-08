# HER-Ai Agent Guidelines

These instructions apply to the entire repository unless a more specific `AGENTS.md`
exists in a subdirectory. All contributors and automation should follow them to
keep the project synchronized across phases and components.

## Goals
- Keep all project phases aligned and synchronized across core, dashboard, docs,
  and infrastructure.
- Ensure changes are testable, documented, and integrated cleanly.

## Required Workflow
1. **Read context first**
   - Check `README.md`, `docs/`, and `config/` for current assumptions and usage.
   - Identify cross-component impact (core, dashboard, docs, CI, infra).

2. **Sync with other project parts**
   - If you change behavior in `her-core`, verify related changes in `dashboard`,
     `docs`, and `docker-compose.yml` where applicable.
   - If you add new configuration, update `.env.example` and relevant docs.

3. **Testing is mandatory**
   - Run the relevant tests or checks for your change and ensure they pass **before**
     creating a PR.
   - If tests cannot run (missing dependencies, environment limits), document the
     reason and any mitigation steps.

4. **Documentation updates**
   - Update `README.md` and/or `docs/` whenever behavior, configuration, or usage
     changes.
   - Keep instructions consistent across docs and code.

5. **Operational readiness**
   - Ensure services can start cleanly with `docker-compose.yml`.
   - Verify health checks and logs for affected services.

## Pull Request Expectations
- Provide a clear summary of changes, tests run, and any follow-up needed.
- Call out cross-component synchronization steps explicitly.

## Dependency Notes
- Keep `openai` version constraints compatible with both `crewai` and `langchain-openai`
  to avoid resolver conflicts (e.g., prefer `openai>=1.13.3,<2.0.0`).

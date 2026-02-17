# Future Implementation Roadmap

This roadmap is forward-looking and organized into three delivery phases.

## Phase 1 - Short-Term (Next 1-3 Months)

## Milestones and Deliverables

1. Runtime reliability hardening
- Deliverables:
  - improved startup diagnostics for provider and MCP failures
  - clearer degraded-mode notifications in Telegram and dashboard

2. Documentation completeness and consistency
- Deliverables:
  - finalized doc index and per-folder docs
  - configuration examples for common provider combinations
  - operator runbooks for incident triage

3. Scheduler usability improvements
- Deliverables:
  - richer natural-language schedule parsing coverage
  - better validation/error messages for `/schedule add` workflow payloads

## Target Enhancements

- Expand tests around autonomous sandbox loop guardrails.
- Add explicit docs for fallback pathways and recovery playbooks.

## Phase 2 - Medium-Term (3-6 Months)

## Major Features

1. Multi-channel interface expansion
- Add additional chat channels beyond Telegram with shared memory semantics.

2. Enhanced memory governance
- Add retention, archival, and user-directed memory controls.

3. Advanced dashboard operations
- Role-aware admin views and richer historical analytics.

## Refactoring Tasks

- Split large Telegram handler module into domain-oriented submodules.
- Extract scheduler workflow evaluator into dedicated component with tighter typing.
- Consolidate duplicated runtime paths (`her-core/main.py` and legacy `her-core/telegram_bot.py`) behind one supported entry strategy.

## Stability and Performance

- Improve response latency under provider failover.
- Add load-focused runtime checks and memory query profiling.

## Phase 3 - Long-Term (6-12 Months)

## Visionary Features

1. Adaptive policy engine
- Policy-driven behavior tuning with explicit safety and style contracts.

2. Plugin ecosystem for tools
- Structured extension model for MCP profiles and custom tools.

3. Explainability layer
- Human-readable rationale summaries for selected decisions and actions.

## Platform Expansion

- Broader deployment targets (managed container platforms, autoscaling profiles).
- More provider presets and memory backend options.

## Scaling and Community

- Contributor templates for modules/tests/docs.
- Public issue labels and RFC workflow for architecture-level changes.
- Versioned documentation and migration guides for major releases.

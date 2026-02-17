# Usage Guide

## Runtime Interfaces

- Telegram bot for user/admin interactions (`her-core/her_telegram/handlers.py`)
- Streamlit dashboard for operations (`dashboard/app.py`)

## Basic User Workflow

1. Send `/start`
2. Ask a normal question
3. Continue conversation to leverage memory context

Example:
```text
User: I prefer concise replies.
User: Help me plan my day.
```

## Admin Workflow

Admin commands:
- `/status`
- `/personality`
- `/memories`
- `/reflect`
- `/reset`
- `/mcp`
- `/schedule ...`
- `/example ...`

Examples:
```text
/schedule list
/schedule run memory_reflection
/schedule add hydrate reminder daily at=09:00 timezone=UTC message='Drink water' notify_user_id=123456789
```

## Natural-Language Scheduling

HER parses scheduling intents from regular messages.

Examples:
- `Remind me in 30 minutes to submit the report.`
- `Every weekday at 08:30 remind me to plan priorities.`
- `Check BTC every 5 minutes and notify me if it rises 10%.`

## Tooling and Sandbox Examples

Examples:
- `Check SSL certificate expiry for github.com.`
- `Run DNS lookup for openai.com.`
- `Inspect headers for https://example.com.`

These flow through MCP and/or sandbox tools in `her-core/her_mcp/tools.py` and `her-core/her_mcp/sandbox_tools.py`.

## Language and Continuity Behavior

Current handlers include:
- conversation-context continuity,
- multilingual request handling,
- language-aligned confirmations for scheduling and automation flows.

Reference implementation: `her-core/her_telegram/handlers.py`.

## Dashboard Workflow

Open `http://localhost:8501` and use pages for:
- Overview/metrics
- Logs
- Executors
- Jobs
- Decisions
- Memory
- Health

Detailed operations: `docs/admin-tooling.md`.

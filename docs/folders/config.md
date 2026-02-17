# Folder Reference: config

## Purpose

Central YAML configuration files for agent behavior, memory, Telegram features, scheduler tasks, and MCP profiles.

## Files

- `config/agents.yaml`
- `config/personality.yaml`
- `config/memory.yaml`
- `config/telegram.yaml`
- `config/rate_limits.yaml`
- `config/scheduler.yaml`
- `config/mcp_servers.yaml`
- `config/mcp_servers.local.yaml`
- `config/twitter.yaml`

## Runtime Resolution

Config file discovery is implemented in `her-core/utils/config_paths.py`, respecting `HER_CONFIG_DIR` and container defaults.

## Validation

- Static coverage in tests (`tests/test_smoke.py`, `tests/test_runtime_guards.py`)
- Runtime checks via `/status`, `/mcp`, and dashboard health pages

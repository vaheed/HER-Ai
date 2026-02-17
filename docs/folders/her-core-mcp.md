# Code Area: her-core/her_mcp

## Purpose

Manages MCP server startup, availability tracking, and tool exposure to runtime agents.

## Files

- `her-core/her_mcp/manager.py` - process lifecycle, env expansion, status tracking
- `her-core/her_mcp/tools.py` - curated tools and capability probing
- `her-core/her_mcp/helpers.py` - async helper functions
- `her-core/her_mcp/sandbox_tools.py` - sandbox command/web/network/security tools
- `her-core/her_mcp/twitter_tools.py` - optional twitter integration tools

## How to Test

```bash
pytest tests/test_runtime_guards.py -q
```

# MCP Guide

## Purpose

HER-Ai uses MCP (Model Context Protocol) to connect runtime agents to external tools in a standardized way.

Core implementation:
- Manager: `her-core/her_mcp/manager.py`
- Tool integration: `her-core/her_mcp/tools.py`
- Helper wrappers: `her-core/her_mcp/helpers.py`

## Profiles

- Default profile: `config/mcp_servers.yaml`
- Local no-key profile: `config/mcp_servers.local.yaml`

Select profile with:
- `MCP_CONFIG_PATH=mcp_servers.yaml`
- or `MCP_CONFIG_PATH=mcp_servers.local.yaml`

## Startup Behavior

- Each enabled server is started with per-server timeout (`MCP_SERVER_START_TIMEOUT_SECONDS`).
- Missing required env placeholders mark server as unavailable instead of crashing full startup.
- Status is exposed in `/mcp` and dashboard runtime capability views.

## Common Troubleshooting

1. Server unavailable due to missing command
- ensure Node/npm available in runtime image (already included in `her-core/Dockerfile`)

2. Unresolved env placeholders
- define variables referenced in MCP profile (for example `POSTGRES_URL`)

3. Timeout at startup
- increase `MCP_SERVER_START_TIMEOUT_SECONDS` if needed and check network/npm availability

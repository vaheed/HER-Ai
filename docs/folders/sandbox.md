# Folder Reference: sandbox

## Purpose

Container image and utilities for isolated command execution and diagnostics.

## Files

- `sandbox/Dockerfile` - sandbox environment definition
- `sandbox/check_pentest_tools.sh` - quick tool availability check script

## Capabilities

Includes tools such as:
- network diagnostics (`ping`, `traceroute`, `dnsutils`, `netcat`)
- security/inspection utilities (`nmap`, `openssl`, `whois`)
- Node/npm MCP packages for local no-key profile

## Test

```bash
docker compose exec sandbox check_pentest_tools
```

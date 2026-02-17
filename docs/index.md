# HER-Ai Documentation

Welcome to the documentation for **HER-Ai**, a personal AI assistant designed for long-term memory, reflection, and evolving personality.

## Quick Links
- [Project Repository](https://github.com/vaheed/HER-Ai)
- [Architecture Overview](architecture.md)
- [Roadmap](roadmap.md)
- [Phase 2 Runtime Status](#phase-2-runtime-status)
- [Phase 1 Build Prompt](phase1_prompt.md)
- [MCP Integration Guide](mcp_guide.md)
- [Admin Dashboard](dashboard.md)
- [Capability Testing Playbook](testing_playbook.md)
- [Prompt Examples](examples.md)

## What is HER-Ai?
HER-Ai is inspired by the movie **"HER"** and focuses on creating a warm, adaptive, and emotionally intelligent assistant. The system is composed of:

- **CrewAI Agents** for conversation, reflection, and personality evolution.
- **Mem0 + PostgreSQL + Redis** for short-term and long-term memory.
- **Docker-based infrastructure** to run the full stack locally or in production.
- **Streamlit Admin Dashboard** for usage metrics and health visibility.
- **Autonomous sandbox execution loop** with strict JSON actions (`command`, `write_to`, `done`).
- **Language-aware continuity**: responses align to the latest user language and keep full conversation context.

For implementation details, follow the Phase 1 prompt and review the architecture documentation.

For hands-on verification of Telegram, MCP, memory, dashboard, and operational behaviors, use the Capability Testing Playbook.


## Phase 2 Runtime Status

Phase 2 scaffolding is now present in the repository:

- Telegram runtime package: `her-core/her_telegram/`
- MCP runtime package: `her-core/her_mcp/`
- Runtime config files:
  - `config/telegram.yaml`
  - `config/rate_limits.yaml`
  - `config/mcp_servers.yaml`

Use the roadmap for completion tracking and open items; use README for environment and startup commands.

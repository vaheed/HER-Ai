# HER - Personal AI Assistant System

> A 24/7 emotionally intelligent AI companion inspired by the movie "HER" - warm, curious, adaptive, and continuously evolving.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Documentation](https://img.shields.io/badge/docs-available-brightgreen)](https://vaheed.github.io/HER-Ai/)

## Vision

HER is not just another chatbot. It is a long-living AI assistant designed to:
- remember conversations and build continuity,
- reflect on interactions for deeper understanding,
- evolve personality traits over time,
- adapt communication style per user,
- expose runtime state through a real-time dashboard,
- feel consistent, not stateless.

Unlike typical assistants, HER is designed for persistent context, adaptive behavior, and operational observability.

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Telegram Bot Token ([create one](https://core.telegram.org/bots/tutorial))
- LLM provider setup (OpenAI, Groq, Ollama, or OpenRouter)

### Installation

1. Clone the repository

```bash
git clone https://github.com/vaheed/HER-Ai.git
cd HER-Ai
```

2. Configure environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

3. Launch HER

```bash
docker compose up -d --build
```

4. Verify installation

```bash
docker compose ps
docker compose logs -f her-bot
```

5. Start chatting
- Open Telegram and message your bot with `/start`

Detailed setup: `docs/installation.md`

## Key Features

### Three-Layer Memory System

- Short-term memory (Redis): recent context with TTL
- Long-term memory (PostgreSQL + pgvector via Mem0): durable semantic memory
- Meta-memory: personality and reinforcement state over time

### Dynamic Personality Evolution

- Core traits: warmth, curiosity, assertiveness, humor, emotional depth
- Evolution inputs: conversations, reflection cycles, admin adjustments, scheduled optimization
- Safety boundaries: bounded updates with stable empathy/safety direction

### Reinforcement Learning Loop

- Per-interaction scoring from feedback and task outcome
- Adaptive communication tendencies (concise/helpful/empathy/initiative)
- Persisted reinforcement events and profile updates
- Weekly self-optimization scheduler task
- Dynamic autonomy profile (engagement score + initiative level)
- Daily reflection loop with bounded initiative adjustment
- Persistent emotional state (curious/reflective/playful/supportive/calm) with gradual decay
- APScheduler persistent SQL job store (restart-safe schedules)
- Optional daily proactive dispatcher with deterministic seeded timing, quiet-hour controls, and DB-enforced daily cap (disabled by default via `HER_PROACTIVE_MESSAGES_ENABLED=false`)

### Agent Architecture (CrewAI)

- Conversation agent: primary interaction flow
- Reflection agent: memory curation
- Personality agent: trait evolution
- Tool agent: external capability execution

### Sandbox Execution Environment

- MCP-backed tool ecosystem
- Web/code/file operations with container isolation
- Built-in network/security diagnostics in sandbox
- Runtime safety guards: timeout, CPU/memory caps, controlled execution loop
- Internal Planner/Skeptic/Verifier debate before action execution

### Dual-Mode Interface

- Admin mode: management commands and full controls
- Public mode: approval/rate-limit controls
- Autonomous action loop using strict JSON action contracts
- Multilingual request interpretation and scheduling support
- Prompt library via `/example`
- OpenAPI adapter for non-Telegram clients (`/api/v1/chat`, Swagger docs)
- OpenAI-compatible API (`/v1/models`, `/v1/chat/completions`) for OpenWebUI and similar chat UIs

### Real-Time Dashboard

- System and capability monitoring
- Memory, scheduler, and execution visibility
- Logs, decisions, metrics, and health views
- Realtime workflow graph (n8n-style) via `http://localhost:8081/workflow?debug=true`

## Documentation

Core documentation in `docs/`:

- `docs/index.md` - documentation index and navigation
- `docs/architecture.md` - architecture and module mapping
- `docs/installation.md` - setup by platform
- `docs/configuration.md` - full environment/config reference
- `docs/usage.md` - user/admin walkthroughs
- `docs/testing.md` - test strategy and commands
- `docs/deployment.md` - container and production guidance
- `docs/admin-tooling.md` - dashboard and operator workflows
- `docs/mcp_guide.md` - MCP server profiles and troubleshooting
- `docs/examples.md` - prompt library and scenarios
- `docs/developer-guidelines.md` - coding and release workflow
- `docs/roadmap.md` - 3-phase implementation roadmap

## Architecture Overview

HER uses a layered architecture separating interfaces, orchestration, memory, and tools:

```text
┌─────────────────────────────────────────────────────────────┐
│                   Experience & Interfaces                    │
│   Telegram Bot (Admin/Public) · Admin Dashboard (Streamlit) │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                Agent Orchestration (CrewAI)                 │
│  Conversation · Reflection · Personality · Tool Agents      │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│            Unified Interpreter & Command Router             │
│  Detect language → normalize intent → SCHEDULE/SANDBOX      │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                 Memory & State (Mem0 + Redis)               │
│  Short-Term Context (Redis TTL) · Long-Term Memory (pgvector) │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                Tools & Execution Environment                │
│  Sandbox Container · MCP Servers · Web/Code/File Operations │
└─────────────────────────────────────────────────────────────┘
```

More details: `docs/architecture.md`

## Technology Stack

| Component | Technology |
|---|---|
| Agent Framework | CrewAI |
| Memory System | Mem0 |
| MCP Integration | Python MCP SDK + community MCP servers |
| LLM Providers | OpenAI, Groq, Ollama, OpenRouter |
| Vector DB | PostgreSQL + pgvector |
| Cache | Redis |
| Telegram Bot | python-telegram-bot |
| Sandbox | Docker Ubuntu container |
| Dashboard | Streamlit |
| Orchestration | Docker Compose |

## Configuration

### Key Environment Variables

```env
# Telegram
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
ADMIN_USER_ID=your_telegram_user_id

# LLM
LLM_PROVIDER=ollama
LLM_ENABLE_FALLBACK=true
LLM_FALLBACK_PROVIDER=ollama
OLLAMA_MODEL=llama3.2:3b

# Database
POSTGRES_USER=her
POSTGRES_PASSWORD=changeme123
POSTGRES_DB=her_memory

# Redis
REDIS_PASSWORD=changeme456

# MCP / Sandbox
MCP_CONFIG_PATH=mcp_servers.yaml
MCP_SERVER_START_TIMEOUT_SECONDS=60
SANDBOX_CONTAINER_NAME=her-sandbox
HER_SANDBOX_PRECHECK_HOST_BINARIES=false
HER_ENABLE_LIVE_WEB_CONTEXT=false
SCHEDULER_DATABASE_URL=
HER_SCHEDULER_STATE_PUBLISH_MIN_INTERVAL_SECONDS=10
HER_SCHEDULER_AUTONOMY_CACHE_TTL_SECONDS=60
HER_WORKFLOW_HTTP_TIMEOUT_SECONDS=12
HER_WORKFLOW_HTTP_RETRIES=2
HER_WORKFLOW_EVENT_QUEUE_MAX_SIZE=5000
HER_WORKFLOW_STATE_PERSIST_INTERVAL_SECONDS=2.0
HER_DECISION_LOG_POSTGRES_ENABLED=true
HER_CONFIG_DIR=/app/config
DOCKER_GID=998
TZ=UTC
USER_TIMEZONE=UTC

# API adapter
API_ADAPTER_ENABLED=true
API_ADAPTER_PORT=8082
API_ADAPTER_MODEL_NAME=her-chat-1
API_ADAPTER_BEARER_TOKEN=
```

Full reference: `docs/configuration.md` and `.env.example`

### Configuration Files

- `config/agents.yaml`
- `config/personality.yaml`
- `config/memory.yaml`
- `config/mcp_servers.yaml`
- `config/telegram.yaml`
- `config/scheduler.yaml`
- `config/rate_limits.yaml`

Runtime note:
- If `/app/config` is read-only, entrypoint falls back to `/app/config.defaults` through `HER_CONFIG_DIR`.
- For runtime edits (`/schedule add`, config writes), mount `/app/config` writable or set `HER_CONFIG_DIR` to a writable directory.

## Testing

Quick checks:

```bash
pytest -q
curl -sS http://localhost:8000
curl -sS http://localhost:8081/workflow/health
curl -sS http://localhost:8082/api/health
curl -sS http://localhost:8082/v1/models
docker compose logs -f her-bot
docker compose exec sandbox check_pentest_tools
```

Testing references:
- `docs/testing.md`
- `docs/testing_playbook.md`

## Usage Examples

### Scheduler (multilingual)

- English: `Remind me every 2 hours to drink water.`
- Persian: `هر روز ساعت ۸ صبح یادآوری کن داروهام رو بخورم.`
- Spanish: `Recuérdame mañana a las 9:30 enviar el informe.`

### Sandbox / Security

- `Run DNS lookup for openai.com.`
- `Run nmap top ports on scanme.nmap.org.`
- `Check SSL handshake for github.com.`

### Natural-language automation

- `If BTC drops 5% from current price, notify me every 10 minutes.`
- `Track this endpoint every 5 minutes and alert on error=true: https://example.com/status`

## Troubleshooting

### Sandbox capability degraded (`Permission denied` on Docker socket)

Set Docker socket group id and restart:

```bash
stat -c '%g' /var/run/docker.sock
# Set DOCKER_GID=<gid> in .env when running non-root her-bot
docker compose up -d --build
```

### Memory and provider issues

- Verify provider credentials and model settings.
- Check logs: `docker compose logs her-bot`.
- Ensure sufficient RAM/CPU for selected model.
- On provider 502/503 responses, fallback provider is used when `LLM_ENABLE_FALLBACK=true`.
- OpenRouter chat + memory is supported via OpenAI-compatible Mem0 adapter path.
- If logs show `model requires more system memory ... than is available`, use a smaller `OLLAMA_MODEL` or increase container memory.
- If Redis/PostgreSQL/Mem0 are temporarily unavailable, HER can continue in degraded mode with fallback memory.

### Telegram connection issues

- Verify `TELEGRAM_BOT_TOKEN`.
- Check network connectivity.
- Review startup logs for retries/timeouts.

## Admin Dashboard

Dashboard URL: `http://localhost:8501`

Includes:
- logs,
- metrics,
- scheduler jobs,
- memory reports,
- runtime capability snapshots,
- health checks.

Dashboard docs: `docs/dashboard.md` and `docs/admin-tooling.md`

## MCP Integration

HER uses MCP for external integrations and tool standardization.

- default profile: `config/mcp_servers.yaml`
- local no-key profile: `config/mcp_servers.local.yaml`
- guide: `docs/mcp_guide.md`

## Contributing

1. Read `AGENTS.md`.
2. Check `docs/roadmap.md` for current priorities.
3. Run tests before PR.
4. Update docs for behavior or configuration changes.

Developer workflow: `docs/developer-guidelines.md`

## License

MIT License - see [LICENSE](LICENSE) for details.

## 🙏 Acknowledgments

- Inspired by the movie "HER" (2013) and its vision of emotionally aware human-AI interaction.
- Built with CrewAI, Mem0, PostgreSQL/pgvector, Redis, and the open-source ecosystem.
- Thanks to all contributors, maintainers, and the MCP community for tools, feedback, and improvements.

## 📞 Support & Resources

- **Documentation**: https://vaheed.github.io/HER-Ai/
- **GitHub Repository**: https://github.com/vaheed/HER-Ai
- **Issues**: [GitHub Issues](https://github.com/vaheed/HER-Ai/issues) for bug reports and feature requests
- **Discussions**: [GitHub Discussions](https://github.com/vaheed/HER-Ai/discussions) for ideas, Q&A, and roadmap conversations

---

**Made with ❤️ by developers who believe AI should be warm, not cold**

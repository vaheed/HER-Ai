# HER - Personal AI Assistant System

> A 24/7 emotionally intelligent AI companion inspired by the movie "HER" - warm, curious, adaptive, and continuously evolving.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Documentation](https://img.shields.io/badge/docs-available-brightgreen)](https://vaheed.github.io/HER-Ai/)

## 🌟 Vision

HER is not just another chatbot. It's a long-living AI assistant designed to:
- **Remember** conversations and develop genuine continuity
- **Reflect** on experiences to form deeper understanding
- **Evolve** personality traits through interactions
- **Adapt** communication style per user over time
- **Monitor** internal state via real-time dashboard
- **Feel** consistent, not stateless or robotic

Unlike typical AI assistants, HER learns, grows, and maintains authentic warmth across all interactions.

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Telegram Bot Token ([Get one here](https://core.telegram.org/bots/tutorial))
- LLM Provider (OpenAI/Groq/Ollama/OpenRouter)

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/vaheed/HER-Ai.git
cd HER-Ai
```

2. **Configure environment**
```bash
cp .env.example .env
# Edit .env with your credentials
```

3. **Launch HER**
```bash
docker compose up -d --build
```

4. **Verify installation**
```bash
docker compose ps
docker compose logs -f her-bot
```

5. **Start chatting**
- Open Telegram and message your bot: `/start`
- Begin your journey with HER

> **📖 For detailed setup instructions**, see the [Quick Start Guide](#-documentation) or [Testing Playbook](docs/testing_playbook.md)

## ✨ Key Features

### 💭 Three-Layer Memory System
- **Short-Term Memory (Redis)**: Recent conversations (24h), fast retrieval
- **Long-Term Memory (PostgreSQL + pgvector)**: Semantic memories, user facts, emotional patterns
- **Meta-Memory**: Personality state, traits evolution, growth markers

### 🎭 Dynamic Personality Evolution
- **5 Core Traits**: Warmth, Curiosity, Assertiveness, Humor, Emotional Depth (0-100 scale)
- **Evolution Mechanisms**: Conversation-driven, reflection-driven, admin-tuned, time-based
- **Safety Constraints**: Bounded traits, immutable empathy/safety values

### 🤖 Agent Architecture (CrewAI)
- **Conversation Agent**: Primary interaction handler
- **Reflection Agent**: Analyzes conversations, decides what to remember
- **Personality Evolution Agent**: Adjusts traits based on interactions
- **Tool Agent**: Executes web searches, code, file operations

### 🔧 Sandbox Execution Environment
- **MCP Servers**: Pre-built integrations for 1000+ services
- **Web Search**: DuckDuckGo, Brave, Serper API via MCP
- **Code Execution**: Python, Node.js, Bash via sandbox container
- **Network/Security Diagnostics**: nmap, DNS tools, ping, traceroute, SSL checks (no API keys)
- **File Operations**: Local, Google Drive, Dropbox via MCP
- **Safe & Isolated**: All operations run in isolated Docker sandbox container

### 📱 Dual-Mode Interface
- **Admin Mode**: Full access, personality tuning, memory management
- **Public Mode**: User interactions, approval-based features

### 📊 Real-Time Dashboard
- **Monitoring**: Conversation logs, agent activity, system health
- **Visualization**: Personality traits, memory statistics, usage metrics
- **Management**: Manual personality tuning, memory exploration

## 📚 Documentation

Comprehensive documentation is available in the `docs/` directory:

### Core Documentation
- **[Architecture Overview](docs/architecture.md)** - Complete system architecture, design patterns, and technical specifications
- **[MCP Integration Guide](docs/mcp_guide.md)** - Model Context Protocol integration, server configuration, and tool usage
- **[Admin Dashboard](docs/dashboard.md)** - Dashboard features, usage, and configuration
- **[Testing Playbook](docs/testing_playbook.md)** - Step-by-step capability testing and validation guide

### Project Management
- **[Project Roadmap](docs/roadmap.md)** - Development phases, milestones, and implementation timeline
- **[Agent Guidelines](AGENTS.md)** - Development workflow, testing requirements, and contribution guidelines
- **[Documentation Index](docs/index.md)** - Central documentation hub with quick links

### Additional Resources
- **[Phase 1 Prompt](docs/phase1_prompt.md)** - Original build specification and requirements

## 🏗️ Architecture Overview

HER is designed as a layered system that separates user interaction, agent orchestration, memory, and tool execution:

```
┌─────────────────────────────────────────────────────────────┐
│                   Experience & Interfaces                    │
│   Telegram Bot (Admin/Public) · Admin Dashboard (Streamlit)  │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                Agent Orchestration (CrewAI)                  │
│  Conversation · Reflection · Personality · Tool Agents       │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                 Memory & State (Mem0 + Redis)                │
│  Short-Term Context (Redis TTL) · Long-Term Memory (pgvector) │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                Tools & Execution Environment                 │
│  Sandbox Container · MCP Servers · Web/Code/File Operations  │
└─────────────────────────────────────────────────────────────┘
```

> **📖 For detailed architecture documentation**, see [docs/architecture.md](docs/architecture.md)

## 🛠️ Technology Stack

| Component | Technology |
|-----------|-----------|
| **Agent Framework** | CrewAI |
| **Memory System** | Mem0 |
| **MCP Integration** | Official Python SDK + 1000+ community servers |
| **LLM Providers** | OpenAI GPT-4, Groq (Llama-3, Mixtral), Ollama, OpenRouter |
| **Vector DB** | PostgreSQL + pgvector |
| **Short-term Cache** | Redis |
| **Telegram Bot** | python-telegram-bot |
| **Sandbox** | Docker Ubuntu Container |
| **Web Search** | DuckDuckGo, Serper API |
| **Twitter Integration** | Tweepy (Twitter API v2) |
| **Task Scheduler** | Custom async scheduler (cron-like) |
| **Dashboard** | Streamlit |
| **Orchestration** | Docker Compose |

## 🔧 Configuration

### Environment Variables

Key environment variables (see `.env.example` for complete list):

```env
# Telegram
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
ADMIN_USER_ID=your_telegram_user_id

# LLM Provider (choose one)
LLM_PROVIDER=ollama  # or openai, groq, openrouter
OLLAMA_MODEL=llama3.2:3b

# Database
POSTGRES_USER=her
POSTGRES_PASSWORD=her_secure_password
POSTGRES_DB=her_memory

# Redis
REDIS_PASSWORD=redis_secure_password

# MCP / Sandbox
MCP_CONFIG_PATH=mcp_servers.yaml
MCP_SERVER_START_TIMEOUT_SECONDS=60
SANDBOX_CONTAINER_NAME=her-sandbox
DOCKER_GID=998
TZ=UTC
```

### Configuration Files

Configuration files are located in `config/`:

- `config/agents.yaml` - Agent definitions and behavior
- `config/personality.yaml` - Personality traits and evolution settings
- `config/memory.yaml` - Memory system configuration
- `config/mcp_servers.yaml` - MCP server integrations
- `config/telegram.yaml` - Telegram bot settings
- `config/scheduler.yaml` - Scheduled tasks configuration

> **📖 For detailed configuration options**, see [docs/architecture.md](docs/architecture.md#-configuration-management)
>
> Runtime note: inside the container, when `/app/config` is read-only, entrypoint automatically falls back to `/app/config.defaults` via `HER_CONFIG_DIR` so startup continues with valid defaults.

Set `MCP_CONFIG_PATH=mcp_servers.local.yaml` if you want the no-key local MCP profile.

## 🧪 Testing

After installation, validate your setup using the comprehensive testing playbook:

```bash
# Follow the step-by-step guide
cat docs/testing_playbook.md
```

Quick validation:
```bash
# Check health
curl http://localhost:8000

# View logs
docker compose logs -f her-bot

# Access dashboard
open http://localhost:8501
```

> **📖 For complete testing procedures**, see [docs/testing_playbook.md](docs/testing_playbook.md)

## 🐛 Troubleshooting

Common issues and solutions:

### Docker Compose Build Errors
- Ensure you're using the latest `docker-compose.yml` from the repository
- Check that all required directories exist

### Sandbox Capability Degraded (`Permission denied` on Docker socket)
- Ensure `DOCKER_GID` matches your host Docker socket group id:
  - `stat -c '%g' /var/run/docker.sock`
- Set that value in `.env` as `DOCKER_GID=<gid>` and restart:
  - `docker compose up -d --build`

### Memory/LLM Provider Issues
- Verify your LLM provider credentials are correct
- Check container logs: `docker compose logs her-bot`
- Ensure sufficient system resources (RAM/CPU)
- **Ollama Memory Errors**: If logs show `model requires more system memory ... than is available`, your Ollama chat model is too large for current container RAM; switch to a smaller `OLLAMA_MODEL` (or raise memory limits) to restore long-term memory writes/search quality
- **Graceful Degradation**: If PostgreSQL/Mem0/Redis are temporarily unavailable at startup, HER now continues in degraded mode using in-process fallback memory so the agent can still reply while infra recovers

### Telegram Connection Issues
- Verify `TELEGRAM_BOT_TOKEN` is correct
- Check network connectivity
- Review startup logs for connection errors

> **📖 For detailed troubleshooting**, see the [Testing Playbook](docs/testing_playbook.md) or check [GitHub Issues](https://github.com/vaheed/HER-Ai/issues)

## 📊 Admin Dashboard

Access the admin dashboard at `http://localhost:8501` for:
- Real-time conversation monitoring
- Personality trait visualization
- Memory explorer and search
- Agent activity logs
- Usage metrics and analytics
- Manual personality tuning

> **📖 For dashboard documentation**, see [docs/dashboard.md](docs/dashboard.md)

## 🔌 MCP Server Integration

HER uses the Model Context Protocol (MCP) for external integrations, providing access to 1000+ pre-built servers:

- **Web Search**: DuckDuckGo, Brave Search, Google Search (via Serper)
- **File Systems**: Local files, Google Drive, Dropbox, OneDrive
- **Databases**: PostgreSQL, MySQL, SQLite, MongoDB
- **Communication**: Slack, Discord, Telegram
- **Development**: GitHub, GitLab, Docker
- **Productivity**: Google Calendar, Notion, Obsidian

> **📖 For MCP integration guide**, see [docs/mcp_guide.md](docs/mcp_guide.md)

## 🤝 Contributing

Contributions are welcome! Please follow these guidelines:

1. Read [AGENTS.md](AGENTS.md) for development workflow
2. Check [docs/roadmap.md](docs/roadmap.md) for current priorities
3. Ensure tests pass before submitting PRs
4. Update documentation for any behavior changes

> **📖 For contribution guidelines**, see [AGENTS.md](AGENTS.md)

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

## 🙏 Acknowledgments

- Inspired by the movie "HER" (2013)
- Built with CrewAI, Mem0, and the open-source community
- Thanks to all contributors and the MCP community

## 📞 Support & Resources

- **Documentation**: https://vaheed.github.io/HER-Ai/
- **GitHub Repository**: https://github.com/vaheed/HER-Ai
- **Issues**: [GitHub Issues](https://github.com/vaheed/HER-Ai/issues)
- **Discussions**: [GitHub Discussions](https://github.com/vaheed/HER-Ai/discussions)

---

**Made with ❤️ by developers who believe AI should be warm, not cold**

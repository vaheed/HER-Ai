# HER - Personal AI Assistant System

> A 24/7 emotionally intelligent AI companion inspired by the movie "HER" - warm, curious, adaptive, and continuously evolving.

## 🌟 Vision

HER is not just another chatbot. It's a long-living AI assistant designed to:
- **Remember** conversations and develop genuine continuity
- **Reflect** on experiences to form deeper understanding
- **Evolve** personality traits through interactions
- **Adapt** communication style per user over time
- **Monitor** internal state via real-time dashboard
- **Feel** consistent, not stateless or robotic

Unlike typical AI assistants, HER learns, grows, and maintains authentic warmth across all interactions.

## 🏗️ Architecture Overview

HER is designed as a layered system that separates user interaction, agent
orchestration, memory, and tool execution. This makes it easier to scale,
observe, and evolve each component independently.

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

**Key characteristics**
- **Separation of concerns:** Interaction, reasoning, memory, and tools are
  isolated for clarity and maintainability.
- **Operational visibility:** Health checks, logs, and the admin dashboard
  provide real-time system status and usage insight.
- **Extensible integrations:** MCP servers and sandbox tools allow rapid
  expansion of capabilities without changing core logic.

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
- **Code Execution**: Python, Node.js, Bash via MCP
- **File Operations**: Local, Google Drive, Dropbox via MCP
- **Safe & Isolated**: All operations through MCP protocol

### 📱 Dual-Mode Interface
- **Admin Mode**: Full access, personality tuning, memory management
- **Public Mode**: User interactions, approval-based features

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Telegram Bot Token
- OpenAI/Groq API Key
- (Optional) Serper API Key for web search

### Installation

1. **Clone Repository**
```bash
git clone https://github.com/vaheed/HER-Ai.git
cd HER-Ai
```

2. **Configure Environment**
```bash
cp .env.example .env
# Edit .env with your credentials
```

Required environment variables:
```env
# Telegram
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
ADMIN_USER_ID=your_telegram_user_id
TELEGRAM_STARTUP_RETRY_DELAY_SECONDS=10
TELEGRAM_PUBLIC_APPROVAL_REQUIRED=true
TELEGRAM_PUBLIC_RATE_LIMIT_PER_MINUTE=20

# LLM Provider (choose one)
# Local-first (no cloud key required)
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.2:3b
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_HOST=http://ollama:11434
OLLAMA_EMBED_MODEL=nomic-embed-text

# OR OpenAI (optional)
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4o-mini

# OR Groq (optional)
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_API_BASE=https://api.groq.com/openai/v1

# OR OpenRouter (optional)
OPENROUTER_API_KEY=your_openrouter_api_key
OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct
OPENROUTER_API_BASE=https://openrouter.ai/api/v1

# Optional: MCP Servers (add any you want to use)
# Google Drive
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret

# GitHub
GITHUB_TOKEN=your_github_token

# Slack
SLACK_BOT_TOKEN=your_slack_bot_token

# Memory / Embeddings
MEMORY_VECTOR_PROVIDER=pgvector
MEMORY_COLLECTION_NAME=memories
# Keep bot responsive if Mem0/Ollama memory writes fail under low RAM
MEMORY_STRICT_MODE=false

# Local-first embeddings (low CPU)
EMBEDDER_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIMENSIONS=768

# Database
POSTGRES_USER=her
POSTGRES_PASSWORD=her_secure_password
POSTGRES_DB=her_memory

# Redis
REDIS_PASSWORD=redis_secure_password

# App
LOG_LEVEL=INFO
ENVIRONMENT=development
```

3. **Launch HER**
```bash
# Option A: use published images
docker compose pull her-bot dashboard sandbox
docker compose up -d

# Option B: build local source (recommended while developing)
docker compose up -d --build
```
> **Runtime mode tip:** `docker-compose.yml` includes both `image` and `build` for app services, so you can either pull published images or rebuild locally from your checked-out source.

4. **Verify Installation**
```bash
# Check all containers are running
docker compose ps

# View logs
docker compose logs -f her-bot
```

### Startup Reliability Notes
- Crew orchestration tasks now include explicit `expected_output` metadata so they are compatible with newer CrewAI/Pydantic validation rules.
- Telegram polling is configured with `stop_signals=None` because the bot runs in a background thread; this avoids `set_wakeup_fd only works in main thread` runtime failures.
- Telegram startup now retries when Telegram API calls time out (`telegram.error.TimedOut`/`NetworkError`), so transient upstream outages no longer crash `her-bot` startup.
- Runtime shutdown now handles the Telegram `NetworkError` variant `cannot schedule new futures after shutdown` as a clean stop signal, avoiding noisy stack traces during service/container termination.
- Startup warm-up checks are now **disabled by default** (`STARTUP_WARMUP_ENABLED=false`) so token-limited providers do not crash `her-bot` during boot; enable only when you explicitly want startup self-tests.
- You can disable Telegram polling entirely with `TELEGRAM_ENABLED=false` (useful for local core testing without Telegram connectivity).
- Long-term memory writes/searches now fail open by default (`MEMORY_STRICT_MODE=false`): if Mem0/LLM memory operations fail (for example low-RAM Ollama errors), HER logs a warning, keeps short-term Redis context, and still replies to users. Set `MEMORY_STRICT_MODE=true` to restore fail-fast behavior.
- Telegram chat replies now automatically retry transient LLM API failures (rate limits/timeouts/connection blips) and return a friendly retry-wait message instead of a stack trace when provider token limits are hit.
- Telegram public mode now supports admin approval (`/approve <user_id>`) and per-minute rate limiting; users can run `/mode` to inspect their access state.
- If logs show `model requires more system memory ... than is available`, your Ollama chat model is too large for current container RAM; switch to a smaller `OLLAMA_MODEL` (or raise memory limits) to restore long-term memory writes/search quality.

## ✅ Step-by-Step Ability Test (End-to-End)

After startup, use this short sequence to test HER abilities in order:

1. Infrastructure + health
```bash
docker compose ps
curl -sS http://localhost:8000
```

2. Telegram baseline
- `/start`
- `/help`
- `Hello HER, remember I like jasmine tea.`

3. Admin controls (admin account)
- `/status`
- `/personality`
- `/memories`
- `/mcp`
- `/reset`

4. Public-mode safety
- From a non-admin account, send messages quickly to validate throttling behavior.

5. MCP capability probe
- Ask: `Search the web for latest AI news and summarize in 3 bullets.`
- Verify `/mcp` returns server statuses for configured MCP servers.

6. Dashboard
- Open `http://localhost:8501` and verify app loads with operational panels.

For a complete, copy/paste runbook (including expected outcomes and negative-path checks), see: **`docs/testing_playbook.md`**.

5. **Start Chatting (Telegram)**
- Make sure your Telegram credentials are set in `.env` (`TELEGRAM_BOT_TOKEN`, `ADMIN_USER_ID`).
- If `TELEGRAM_PUBLIC_APPROVAL_REQUIRED=true`, admins can approve users with `/approve <user_id>`.
- Restart the service: `docker compose up -d --force-recreate her-bot`
- Open Telegram
- Message your bot: `/start`
- Message your bot normally (for example: `hey, are you there?`) and HER now generates a contextual conversational reply using recent context + memory retrieval, instead of only sending an acknowledgement.
- Begin your journey with HER

## 🧠 Local Embeddings (Ollama, low CPU)

HER now supports local embeddings and local LLM inference through Ollama by default,
so OpenAI is optional.

1. Start stack:
```bash
# Pull mode
docker compose up -d

# or local build mode
docker compose up -d --build
```

2. Wait for pre-pull bootstrap to complete:
```bash
docker compose logs -f ollama-init
```

`ollama-init` automatically pulls both models on startup:
- chat model: `${OLLAMA_MODEL}` (default `llama3.2:3b`)
- embedding model: `${OLLAMA_EMBED_MODEL}` (default `nomic-embed-text`)

3. Verify models are ready:
```bash
docker exec -it her-ollama ollama list
```

The compose file includes resource limits for `ollama` (`cpus` and `mem_limit`) to keep
local usage bounded on small servers.

## 🧩 Free MCP Toolkit (preconfigured for sandbox)

HER includes a zero-key MCP profile at `config/mcp_servers.local.yaml` with useful free servers (all no-key):

For container builds that use `sandbox/` as Docker context, this profile is mirrored at `sandbox/mcp_servers.local.yaml`.

- filesystem
- fetch
- memory
- sequential-thinking
- pdf

The sandbox image installs these MCP packages ahead-of-time so they are ready to use.

Package mapping:
- `filesystem` -> `@modelcontextprotocol/server-filesystem`
- `fetch` -> `mcp-fetch-server`
- `memory` -> `@modelcontextprotocol/server-memory`
- `sequential-thinking` -> `@modelcontextprotocol/server-sequential-thinking`
- `pdf` -> `@modelcontextprotocol/server-pdf`

To use inside sandbox/container environments:
```bash
cat /home/sandbox/.config/her/mcp_servers.local.yaml
```

## 🧰 Troubleshooting

### Docker Compose build path error (sandbox missing)
If you see an error like:
```
ERROR: build path /root/her/sandbox either does not exist, is not accessible, or is not a valid URL.
```
ensure you are using the latest `docker-compose.yml` from this repository. The current compose file runs entirely from published images and does **not** require local build contexts such as `sandbox/`. If you're using an older compose file, update it or remove any `build:` blocks so Docker Compose doesn't try to build from missing paths.



### Mem0 `Unsupported vector store provider: pgvector`
If `her-bot` exits with a Mem0 validation error like:
```
Unsupported vector store provider: pgvector
```
make sure the bot image is using a Mem0 release that supports pgvector (`mem0ai>=0.1.x`). This repository pins `mem0ai==0.1.117` and supports both `openai` and local `ollama` embedders; rebuild and redeploy the bot image after pulling latest changes.

### Python dependency resolution conflict (`ResolutionImpossible`)
If dependency installation fails with an error involving `pydantic` and `ollama`, use the pinned core dependency set from this repository. Current compatible pins are:
- `pydantic==2.7.4`
- `ollama==0.3.3`

These pins keep `crewai`, `mem0ai`, `fastapi`, and `langsmith` compatible in the `her-core` environment.

### PostgreSQL `column "id" does not exist` with Groq/Mem0 startup
If logs show errors like:
```
ERROR:  column "id" does not exist
```
this usually means an older bootstrap schema created a legacy `memories` table (`memory_id`, `memory_text`) that conflicts with Mem0's pgvector table shape (`id`, `embedding`, etc.).

Latest startup scripts now handle both cases automatically: they rename only the old app table shape to `memories_legacy`, and they also backfill/add an `id` column for older Mem0-style `memories` tables that have `vector`/`payload` but no `id`. Pull latest changes and restart `her-bot` (or rerun DB init) to apply the migration.

### PostgreSQL `database "her" does not exist` log spam
If your PostgreSQL logs repeatedly show:
```
FATAL:  database "her" does not exist
```
this usually means a health check or client is connecting without an explicit database name, so PostgreSQL falls back to the username (`her`). Ensure your `.env` uses `POSTGRES_DB=her_memory` (or another existing DB), and restart services after updating env values.

## 📊 Admin Dashboard

Access the dashboard at `http://localhost:8501`

Features:
- Real-time conversation monitoring
- Personality trait visualization
- Memory explorer
- Agent activity logs
- Usage metrics (tokens, users, last response)
- Manual personality tuning

## 🔌 MCP Server Integration

HER uses the Model Context Protocol (MCP) for all external integrations, giving you access to thousands of pre-built servers:

### Pre-configured MCP Servers
- **Web Search**: DuckDuckGo, Brave Search, Google Search (via Serper)
- **File Systems**: Local files, Google Drive, Dropbox, OneDrive
- **Databases**: PostgreSQL, MySQL, SQLite, MongoDB
- **Communication**: Slack, Discord, Telegram
- **Development**: GitHub, GitLab, Docker
- **Productivity**: Google Calendar, Notion, Obsidian
- **Browser Automation**: Puppeteer, Playwright

### Adding Custom MCP Servers
```yaml
# config/mcp_servers.yaml
servers:
  - name: "google-drive"
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-google-drive"]
    env:
      GOOGLE_CLIENT_ID: "${GOOGLE_CLIENT_ID}"
      GOOGLE_CLIENT_SECRET: "${GOOGLE_CLIENT_SECRET}"
  
  - name: "postgres"
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-postgres"]
    env:
      DATABASE_URL: "${POSTGRES_URL}"
  
  - name: "github"
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-github"]
    env:
      GITHUB_TOKEN: "${GITHUB_TOKEN}"
```

Browse 1000+ community MCP servers: [Awesome MCP Servers](https://github.com/punkpeye/awesome-mcp-servers)

## 🛠️ Configuration

### Personality Tuning
Edit `config/personality.yaml`:
```yaml
personality:
  warmth: 75
  curiosity: 80
  assertiveness: 60
  humor: 70
  emotional_depth: 85
  
evolution:
  enabled: true
  speed: medium  # slow, medium, fast
  boundaries:
    min: 20
    max: 95
```

### Memory Settings
Edit `config/memory.yaml`:
```yaml
memory:
  short_term_ttl: 86400  # 24 hours
  reflection_frequency: 300  # 5 minutes
  importance_threshold: 0.7
  max_long_term_entries: 10000
```

## 🔒 Security

- All API keys stored in environment variables
- Sandboxed code execution (no host access)
- Redis & PostgreSQL password-protected
- Rate limiting on public mode
- Approval system for sensitive operations

## 📦 Technology Stack

| Component | Technology |
|-----------|-----------|
| **Agent Framework** | CrewAI |
| **Memory System** | Mem0 |
| **MCP Integration** | Official Python SDK + 1000+ community servers |
| **LLM Providers** | OpenAI GPT-4, Groq (Llama-3, Mixtral) |
| **Vector DB** | PostgreSQL + pgvector |
| **Short-term Cache** | Redis |
| **Telegram Bot** | python-telegram-bot |
| **Sandbox** | Docker Ubuntu Container |
| **Web Search** | DuckDuckGo, Serper API |
| **Dashboard** | Streamlit |
| **Orchestration** | Docker Compose |

## 🎯 Usage Examples

### Admin Mode Commands
```
/status - View HER's current state
/personality - Adjust personality traits
/memories - Browse stored memories
/reflect - Trigger manual reflection
/reset - Clear conversation context (keeps long-term memory)
```

### Public Mode
Public users interact naturally. Admin can:
- Approve/deny specific features per user
- Monitor conversations
- Set usage limits

### Example Conversations

**Emotional Support:**
```
User: I'm feeling overwhelmed with work
HER: I can sense you're carrying a lot right now. Want to talk about 
     what's weighing on you most? Sometimes just naming it helps.
```

**Continuous Learning:**
```
User: I love hiking on weekends
[Stored: User enjoys hiking, weekend activity preference]

Later...
HER: With the weather looking nice this weekend, are you planning 
     any hikes? You mentioned loving those.
```

## 📦 Build & Publish (GitHub Container Registry)

The Docker Compose file is wired to GHCR images for `her-bot`, `her-dashboard`, and `her-sandbox`.

**Automated tags via GitHub Actions (`.github/workflows/ci.yml`):**
- push to `main`: publishes `latest` + `sha-*` tags
- push tag like `v0.0.1`: publishes `v0.0.1` and `0.0.1` tags (+ `sha-*`)
- publish a GitHub Release with tag `v0.0.1`: also publishes matching image tags

```bash
# Build images
docker compose build

# Login to GHCR
echo $GITHUB_TOKEN | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin

# Push images
docker compose push
```

## 🤝 Contributing

Contributions welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

## 🙏 Acknowledgments

- Inspired by the movie "HER" (2013)
- Built with CrewAI, Mem0, and the open-source community
- Thanks to all contributors

## 📞 Support

- **Documentation**: https://vaheed.github.io/HER-Ai/
- **Issues**: [GitHub Issues](https://github.com/vaheed/HER-Ai/issues)
- **Discussions**: [GitHub Discussions](https://github.com/vaheed/HER-Ai/discussions)
- **Email**: support@her-ai.dev

---

**Made with ❤️ by developers who believe AI should be warm, not cold**

## Phase 2: Telegram + MCP Integration

> Dependency note: `her-core/requirements.txt` pins `mcp==1.26.0` because `0.9.0` is no longer available on PyPI in current environments.

Phase 2 adds a structured Telegram interface and MCP server orchestration:

- Telegram bot package under `her-core/telegram/` with admin/public command handling and rate limits.
- MCP management package under `her-core/mcp/` for launching configured MCP servers and exposing curated CrewAI tools.
- New config files:
  - `config/mcp_servers.yaml`
  - `config/telegram.yaml`
  - `config/rate_limits.yaml`

### New environment variables

- `BRAVE_API_KEY`
- `POSTGRES_URL`

### MCP startup behavior

On startup, HER now:
1. Initializes memory.
2. Starts enabled MCP servers from `config/mcp_servers.yaml`.
3. Creates curated MCP tools and injects them into the conversation agent.
4. Starts Telegram polling with admin/public controls.

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
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
ADMIN_USER_ID=your_telegram_user_id

# LLM Provider (choose one)
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4-turbo-preview
# OR
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=llama3-70b-8192
GROQ_API_BASE=https://api.groq.com/openai/v1

# Optional: MCP Servers (add any you want to use)
# Google Drive
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret

# GitHub
GITHUB_TOKEN=your_github_token

# Slack
SLACK_BOT_TOKEN=your_slack_bot_token

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
docker-compose up -d
```
> **Production tip:** The default `docker-compose.yml` uses published container images, and the app initializes the database schema on first boot, so you can run HER with just the compose file and a `.env` file—no repo build steps required.

4. **Verify Installation**
```bash
# Check all containers are running
docker-compose ps

# View logs
docker-compose logs -f her-bot
```

5. **Start Chatting (Telegram)**
- Make sure your Telegram credentials are set in `.env` (`TELEGRAM_BOT_TOKEN`, `ADMIN_USER_ID`).
- Restart the service: `docker-compose up -d --force-recreate her-bot`
- Open Telegram
- Message your bot: `/start`
- Begin your journey with HER

## 🧰 Troubleshooting

### Docker Compose build path error (sandbox missing)
If you see an error like:
```
ERROR: build path /root/her/sandbox either does not exist, is not accessible, or is not a valid URL.
```
ensure you are using the latest `docker-compose.yml` from this repository. The current compose file runs entirely from published images and does **not** require local build contexts such as `sandbox/`. If you're using an older compose file, update it or remove any `build:` blocks so Docker Compose doesn't try to build from missing paths.


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

# Configuration Manual

Configuration is driven by environment variables in `.env` and YAML files under `config/`.

## Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | Primary chat provider (`ollama`, `openai`, `groq`, `openrouter`) |
| `LLM_ENABLE_FALLBACK` | `true` | Enable secondary provider failover for transient upstream errors |
| `LLM_FALLBACK_PROVIDER` | `ollama` | Provider used when primary fails with 502/503 path |
| `OLLAMA_MODEL` | `llama3.2:3b` | Chat model for Ollama provider |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | Ollama service base URL |
| `OLLAMA_HOST` | `http://ollama:11434` | Alternate Ollama endpoint for tooling/init scripts |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Embedding model pulled by `ollama-init` |
| `OPENAI_API_KEY` | - | OpenAI API key |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model name |
| `GROQ_API_KEY` | - | Groq API key |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model |
| `GROQ_API_BASE` | `https://api.groq.com/openai/v1` | Groq OpenAI-compatible endpoint |
| `OPENROUTER_API_KEY` | - | OpenRouter API key |
| `OPENROUTER_MODEL` | `meta-llama/llama-3.3-70b-instruct` | OpenRouter model |
| `OPENROUTER_API_BASE` | `https://openrouter.ai/api/v1` | OpenRouter API endpoint |
| `MEMORY_VECTOR_PROVIDER` | `pgvector` | Mem0 vector store provider |
| `MEMORY_COLLECTION_NAME` | `memories` | Collection/table name |
| `MEMORY_STRICT_MODE` | `false` | If true, memory backend errors are fatal |
| `EMBEDDER_PROVIDER` | `ollama` | Embedder backend (`openai` or `ollama`) |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Embedding model name |
| `EMBEDDING_DIMENSIONS` | `768` | Embedding vector dimensions |
| `POSTGRES_USER` | `her` | PostgreSQL username |
| `POSTGRES_PASSWORD` | `changeme123` | PostgreSQL password |
| `POSTGRES_DB` | `her_memory` | PostgreSQL database |
| `POSTGRES_HOST` | `postgres` | PostgreSQL host |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_URL` | `postgresql://...` | DSN for MCP postgres server |
| `REDIS_HOST` | `redis` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_PASSWORD` | `changeme456` | Redis password |
| `LOG_LEVEL` | `INFO` | Application log level |
| `ENVIRONMENT` | `development` | Environment label |
| `TZ` | `UTC` | Global timezone |
| `STARTUP_WARMUP_ENABLED` | `false` | Optional startup warmup compatibility check |
| `WORKFLOW_DEBUG_SERVER_ENABLED` | `true` | Enable realtime workflow DAG server |
| `WORKFLOW_DEBUG_HOST` | `0.0.0.0` | Workflow debug server bind host |
| `WORKFLOW_DEBUG_PORT` | `8081` | Workflow debug server port |
| `API_ADAPTER_ENABLED` | `true` | Enable HTTP OpenAPI adapter |
| `API_ADAPTER_HOST` | `0.0.0.0` | OpenAPI adapter bind host |
| `API_ADAPTER_PORT` | `8082` | OpenAPI adapter port |
| `API_ADAPTER_BEARER_TOKEN` | `` | Optional bearer token required by API adapter endpoints |
| `API_ADAPTER_MODEL_NAME` | `her-chat-1` | OpenAI-compatible model id exposed by `/v1/models` |
| `TELEGRAM_ENABLED` | `true` | Enable/disable Telegram polling |
| `TELEGRAM_BOT_TOKEN` | - | Telegram bot token |
| `TELEGRAM_STARTUP_RETRY_DELAY_SECONDS` | `10` | Retry delay for transient Telegram network errors |
| `ADMIN_USER_ID` | - | Comma-safe admin ID list source (single env entry accepted) |
| `TELEGRAM_PUBLIC_APPROVAL_REQUIRED` | `true` | Require approval for public users |
| `TELEGRAM_PUBLIC_RATE_LIMIT_PER_MINUTE` | `20` | Public user rate limit |
| `HER_AUTONOMOUS_MAX_STEPS` | `16` | Max autonomous action steps per request |
| `HER_SANDBOX_COMMAND_TIMEOUT_SECONDS` | `60` | Sandbox command timeout |
| `HER_ACTION_INTENT_THRESHOLD` | `0.8` | Minimum confidence required to switch from chat mode to action mode |
| `HER_SANDBOX_CPU_TIME_LIMIT_SECONDS` | `20` | Sandbox CPU time cap |
| `HER_SANDBOX_MEMORY_LIMIT_MB` | `512` | Sandbox memory cap |
| `MCP_CONFIG_PATH` | `mcp_servers.yaml` | MCP profile file name |
| `MCP_SERVER_START_TIMEOUT_SECONDS` | `60` | Timeout per MCP server startup |
| `SANDBOX_CONTAINER_NAME` | `her-sandbox` | Container target for sandbox tools |
| `HER_CONFIG_DIR` | `/app/config` | Runtime config directory override |
| `DOCKER_GID` | `998` | Optional docker group id when non-root runtime |
| `BRAVE_API_KEY` | - | Optional Brave Search MCP key |

## YAML Configuration Files

| File | Purpose |
|---|---|
| `config/agents.yaml` | CrewAI agent role/goal/backstory and runtime settings |
| `config/personality.yaml` | default traits and immutable values |
| `config/memory.yaml` | short/long-term memory limits and dimensions |
| `config/telegram.yaml` | commands, feature flags, admin list |
| `config/rate_limits.yaml` | public/admin rate-limit behavior |
| `config/scheduler.yaml` | recurring and one-off task definitions |
| `config/mcp_servers.yaml` | default MCP profile |
| `config/mcp_servers.local.yaml` | local no-key MCP profile |
| `config/twitter.yaml` | optional twitter automation settings |

## Config Resolution Order

Resolved by `her-core/utils/config_paths.py`:
1. `HER_CONFIG_DIR`
2. `/app/config` or `/app/config.defaults` (order depends on writability)
3. repository `config/`
4. current working directory `config/`

## Configuration Change Workflow

1. Update `.env` and/or `config/*.yaml`.
2. Keep `.env.example` aligned if introducing variables.
3. Restart affected services:
```bash
docker compose up -d --build her-bot dashboard
```
4. Verify with `/status`, `/mcp`, dashboard pages, and service logs.

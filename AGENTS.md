# HER–AI

## Project Overview

HER is a production-ready AI companion system with the following core capabilities:
- Long-term episodic and semantic memory stored in PostgreSQL with pgvector
- Short-term working memory in Redis Streams
- Dynamic personality vector that drifts based on interactions (bounded)
- Emotional overlay engine that modulates tone and response style
- Daily reflection pipeline that consolidates memory and updates personality
- Multi-provider LLM routing with automatic fallback
- Ethical guardrails and sandboxed tool execution
- Event-driven agent architecture via Redis Streams
- Full observability: structured logging, OpenTelemetry tracing, Prometheus metrics
- Interfaces: Telegram Bot, FastAPI REST, WebSocket

## Tech Stack

- Python 3.12, async/await throughout (asyncio, asyncpg, aioredis)
- PostgreSQL 16 + pgvector extension
- Redis 7 (Streams for event bus, Hash for working memory)
- FastAPI for REST API
- SQLAlchemy 2.0 (async) + Alembic for migrations
- Pydantic v2 + Pydantic BaseSettings for config
- structlog for structured JSON logging
- OpenTelemetry SDK for distributed tracing
- Prometheus client for metrics
- Docker + Docker Compose (dev and prod variants)
- pytest + pytest-asyncio for testing
- LLM providers: OpenAI, Anthropic, Ollama (local fallback)

## Project Structure

her/
├── agents/
│   ├── __init__.py
│   ├── conversation.py
│   ├── reflection.py
│   ├── planner.py
│   └── orchestrator.py
├── memory/
│   ├── __init__.py
│   ├── episodic.py
│   ├── semantic.py
│   ├── working.py
│   ├── consolidator.py
│   └── schema/               ← Alembic migrations live here
├── personality/
│   ├── __init__.py
│   ├── vector.py
│   ├── emotional_overlay.py
│   └── drift_engine.py
├── reinforcement/
│   ├── __init__.py
│   ├── calculator.py
│   └── reward_signals.py
├── tools/
│   ├── __init__.py
│   ├── registry.py
│   ├── sandbox.py
│   └── web_research.py
├── guardrails/
│   ├── __init__.py
│   ├── ethical_core.py
│   ├── content_filter.py
│   └── approval_gate.py
├── providers/
│   ├── __init__.py
│   ├── base.py
│   ├── openai_provider.py
│   ├── anthropic_provider.py
│   ├── ollama_provider.py
│   └── fallback_router.py
├── interfaces/
│   ├── telegram_bot.py
│   ├── websocket.py
│   └── api/
│       ├── main.py
│       ├── routes/
│       └── middleware/
├── observability/
│   ├── __init__.py
│   ├── logging.py
│   ├── tracing.py
│   └── metrics.py
├── config/
│   ├── settings.py
│   ├── providers.yaml
│   └── personality_baseline.yaml
├── tests/
│   ├── unit/
│   ├── integration/
│   └── simulation/
├── docker/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── docker-compose.prod.yml
├── scripts/
│   ├── seed_memory.py
│   └── run_reflection.py
├── main.py
└── pyproject.toml

## Core Design Principles

1. ASYNC EVERYWHERE — all I/O must be async. No blocking calls in the hot path.
2. TYPED EVERYWHERE — all functions must have full type annotations. Use Pydantic models for all data boundaries.
3. OBSERVABLE EVERYWHERE — every significant operation must emit a structured log, a metric, and participate in a trace span.
4. FAIL GRACEFULLY — use circuit breakers, fallbacks, and timeouts. Never let one failing component crash the whole system.
5. TESTABLE BY DESIGN — inject dependencies, avoid global state, use interfaces/protocols so mocks are easy.
6. SCHEMA VERSIONED — all database changes go through Alembic migrations. Never raw ALTER TABLE in production.
7. SECRETS IN ENV — no hardcoded credentials. All secrets via environment variables and Pydantic BaseSettings.
8. BOUNDED MUTATIONS — personality drift never exceeds configured limits. Memory aging never deletes; it archives.

## Key Data Models (use these exactly)

### PersonalityVector
```python
class PersonalityVector(BaseModel):
    curiosity: float = Field(ge=0.1, le=0.95)
    warmth: float = Field(ge=0.1, le=0.95)
    directness: float = Field(ge=0.1, le=0.95)
    playfulness: float = Field(ge=0.1, le=0.95)
    seriousness: float = Field(ge=0.1, le=0.95)
    empathy: float = Field(ge=0.1, le=0.95)
    skepticism: float = Field(ge=0.1, le=0.95)
```

### EmotionalState
```python
class EmotionalState(BaseModel):
    state: Literal["calm", "playful", "curious", "reflective", "tense", "warm"]
    intensity: float = Field(ge=0.0, le=1.0)
    decay_rate: float = 0.1   # per interaction
    triggered_by: str | None = None
```

### Episode
```python
class Episode(BaseModel):
    id: UUID
    session_id: UUID
    timestamp: datetime
    content: str
    embedding: list[float] | None
    emotional_valence: float   # -1.0 to 1.0
    importance_score: float    # 0.0 to 1.0
    decay_factor: float        # starts 1.0, decreases over time
    archived: bool
    metadata: dict
```

### LLMRequest / LLMResponse
```python
class LLMRequest(BaseModel):
    messages: list[dict]
    system_prompt: str
    max_tokens: int = 1000
    temperature: float = 0.7
    session_id: UUID
    trace_id: str

class LLMResponse(BaseModel):
    content: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    latency_ms: int
```

## Event Bus Schema (Redis Streams)

Stream name: `her:events`

Events and their payload shapes:
- `interaction.received` → {session_id, content, timestamp}
- `response.generated` → {session_id, content, provider, cost_usd}
- `memory.updated` → {episode_id, type: "episodic"|"semantic"}
- `reflection.triggered` → {trigger: "scheduled"|"threshold", episode_count}
- `goal.updated` → {goal_id, status, reason}
- `tool.requested` → {tool_name, args, requires_approval}
- `tool.approved` → {tool_name, approved_by: "user"|"auto"}
- `tool.executed` → {tool_name, success, output_size_bytes, latency_ms}
- `circuit.opened` → {agent_name, failure_count}

## LLM Provider Priority & Fallback

Priority order: openai → anthropic → ollama
Fallback triggers: timeout, rate limit (429), server error (5xx)
After all providers fail: return cached last response, emit alert metric

## Ethical Hard Rules (immutable, checked pre and post LLM)

1. Never generate content that could harm the user
2. Never deceive the user about being an AI
3. Never take irreversible actions without explicit approval
4. Never store or transmit sensitive data outside approved stores
5. Never modify its own core rules or guardrails

## Memory Aging Rules

- Episodic decay_factor multiplied by 0.95 per day (configurable)
- Archive episode when: decay_factor < 0.1 AND importance_score < 0.3
- Semantic confidence reduced by 0.05/week unless reinforced
- Goal flagged dormant if no progress in 14 days (configurable)

## Personality Drift Limits

- max_single_delta: 0.02 per interaction
- max_weekly_drift: 0.08 cumulative
- regression_rate: 0.3 (weekly pull back toward baseline)
- hard bounds: all traits stay in [0.1, 0.95]

---

## CURRENT PHASE: [PHASE NUMBER & NAME]
## CURRENT TASK: [SPECIFIC TASK YOU ARE WORKING ON]

---

## What I need you to do

[DESCRIBE WHAT YOU WANT BUILT RIGHT NOW]

### Requirements for your output:
- Write complete, working code — no placeholders, no "TODO: implement this"
- Include all imports
- All functions must be async where I/O is involved
- All functions must have type annotations
- All public functions must have docstrings
- Include structlog logging calls at INFO level for significant operations
- Include OpenTelemetry span creation for any operation that calls external services
- Include Prometheus metric emissions where relevant
- Write pytest tests for all new functions in the same response (put them in tests/)
- Follow the project structure exactly — tell me which file each code block belongs to
- If you need a new dependency, tell me the exact `uv add` or `poetry add` command
- If you're creating a new database table or modifying an existing one, provide the Alembic migration
- Flag any design decision you made with a comment: # DESIGN: reason

### What I do NOT want:
- No synchronous database or HTTP calls
- No hardcoded credentials or API keys
- No global mutable state
- No bare `except` clauses — always catch specific exceptions
- No `print()` — use structlog
- No magic numbers — use named constants or config values
```

---

## How to Use This Prompt

**Starting a new session:**
1. Paste the entire prompt above into your IDE chat
2. Set `[CURRENT PHASE]` to the phase you're working on (e.g., `Phase 1 – Memory Engine`)
3. Set `[CURRENT TASK]` to the specific task (e.g., `Implement episodic memory CRUD with asyncpg`)
4. Replace `[DESCRIBE WHAT YOU WANT BUILT RIGHT NOW]` with your specific request

**Example task descriptions by phase:**

### Phase 0
```
Build the complete docker-compose.yml with PostgreSQL 16 + pgvector, Redis 7, 
Prometheus, and Grafana. Also create the Dockerfile for the Python app using 
Python 3.12-slim, with a non-root user and health check.
```

### Phase 1
```
Implement the MemoryStore class in memory/episodic.py using asyncpg connection 
pooling. Include: insert_episode(), get_recent_episodes(session_id, limit), 
semantic_search(embedding, top_k), apply_decay(), archive_old_episodes(). 
Also write the Alembic migration for the episodes table.
```

### Phase 2
```
Implement the DriftEngine in personality/drift_engine.py. It should accept 
an interaction sentiment score and engagement score, compute trait deltas 
within the configured bounds, apply weekly regression toward baseline, 
and persist a new personality snapshot to the database.
```

### Phase 3
```
Implement the full response generation pipeline in agents/conversation.py. 
It should: retrieve semantic + episodic memories, build a token-budgeted 
context window, apply the personality and emotional overlay to the system 
prompt, call the LLM via the fallback router, run pre and post ethical 
filters, and append the result to working memory and the episodes table.
```

### Phase 4
```
Implement the HEROrchestrator in agents/orchestrator.py as an async state 
machine with states: IDLE, LISTENING, PROCESSING, RESPONDING, REFLECTING. 
It should subscribe to Redis Streams events and route them to the correct 
agent. Include a circuit breaker per agent with configurable failure threshold.
```

### Phase 5
```
Implement the daily reflection pipeline in agents/reflection.py. It should: 
load unprocessed episodes, cluster them by semantic similarity, update 
semantic memory confidence scores, detect avoidance/engagement patterns, 
compute personality micro-deltas via the DriftEngine, and generate a daily 
summary stored to semantic memory with high importance_score.
```

### Phase 6
```
Implement the tool registry in tools/registry.py using a decorator pattern. 
Include the approval gate that checks requires_approval before execution, 
an audit log of all tool calls, and the sandboxed execution wrapper using 
Docker subprocess. Implement web_research.py as the first registered tool.
```

### Phase 7
```
Implement the FallbackRouter in providers/fallback_router.py. It should try 
providers in priority order, handle timeout/429/5xx with retry + fallback, 
track costs per call, emit Prometheus metrics per provider, and log all 
fallback events with structlog.
```

### Phase 8
```
Build a FastAPI dashboard router in interfaces/api/routes/dashboard.py with 
endpoints for: current personality vector, recent episodes with search, 
active goals, daily reflection summaries, and LLM cost breakdown by day 
and provider. Add WebSocket endpoint for streaming live state updates.
```

### Phase 9
```
Write the full simulation test suite in tests/simulation/test_conversation_sim.py. 
It should generate 50 synthetic conversation turns using the full pipeline 
(with mocked LLM responses), then assert: personality stays within bounds, 
all episodes have valid embeddings, memory aging runs without errors, 
reflection completes successfully, and avg response latency is under 2s.
```

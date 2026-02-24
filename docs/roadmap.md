# HER – Production-Ready AI Companion
## Improved Architecture & Roadmap

---

## Implementation Status (Updated: February 24, 2026)

### Phase 0 – Foundation & DevOps

- [x] Setup `pyproject.toml` with build/runtime/dev dependencies
- [ ] Configure `pre-commit` hooks (`ruff`, `black`, `mypy`)  
  Current state: lint/type/test tooling exists; pre-commit hook wiring not added yet.
- [x] Docker Compose stack includes PostgreSQL 16 (`pgvector` image), Redis 7, Prometheus, Grafana, Jaeger
- [x] Pydantic `BaseSettings` + `.env.example` + provider routing config
- [x] Top-level package scaffold and module boundaries
- [x] Structured logging (`structlog`) + OpenTelemetry tracing bootstrap + Prometheus metrics endpoint
- [x] GitHub Actions test/deploy workflows
- [x] LLM provider abstraction and fallback router (OpenAI, Anthropic, Ollama)
- [x] Hello flow script (`scripts/hello_her.py`)

### Phase 1 – Memory Engine

- [x] Alembic setup and initial migration for production memory schema  
  Implemented: `alembic.ini`, `her/memory/schema/env.py`, `her/memory/schema/versions/20260224_0001_initial_memory_schema.py`
- [x] Async SQLAlchemy database layer (`MemoryDatabase`) and CRUD store (`MemoryStore`)
- [x] Episodic CRUD via persistent store (`episodes` table)
- [x] Semantic memory upsert + vector search interface (`semantic_memory` table)
- [x] Redis Hash working memory with TTL + in-process fallback
- [x] Consolidator service for overlapping semantic concepts
- [x] Aging pipeline implementation (episodic decay/archive + semantic decay + dormant goals)
- [x] Cost tracking persistence (`llm_usage_log`)
- [x] API wired to persistent memory services
- [x] Operational scripts for seeding/reflection/aging
- [ ] End-to-end integration test against live Postgres+Redis in CI  
  Current state: unit-level and local app checks are green; no live service integration test job yet.

### Phase 2 – Personality & Emotional Layer

- [x] Personality baseline traits + drift limits config loaded from YAML
- [x] Drift engine enforces per-interaction bounds and weekly cumulative caps
- [x] Personality snapshot persisted before interaction drift and weekly regression
- [x] Emotional transition + decay engine implemented
- [x] Emotional overlay stacked with personality to produce final tone vector
- [x] Dynamic personality-aware system prompt builder integrated into conversation flow
- [x] Reflection path uses weekly regression via personality manager
- [x] Unit tests added for drift edge cases, emotional overlay, and personality snapshot behavior
- [x] Personality state reload from latest DB snapshot on service boot

---

## Core Architecture Improvements

Before diving into phases, here are the key architectural upgrades over the original plan:

- **Event-driven core** using an internal message bus (Redis Streams or Kafka-lite) so agents don't block each other
- **Agent orchestration** via a lightweight state machine (not ad-hoc function calls)
- **Observability-first** — structured logging, tracing (OpenTelemetry), and metrics from Day 1
- **Schema versioning** for memory tables from the start (Alembic migrations)
- **Secrets management** via environment-scoped `.env` + HashiCorp Vault-ready config
- **CI/CD pipeline** defined early, not bolted on later
- **Rate limiting & cost tracking** on all LLM calls from Phase 0

---

## Revised Project Structure

```
her/
├── agents/
│   ├── conversation.py
│   ├── reflection.py
│   ├── planner.py
│   └── orchestrator.py          # NEW: state machine coordinator
├── memory/
│   ├── episodic.py
│   ├── semantic.py
│   ├── working.py               # Redis-backed short-term
│   ├── schema/                  # NEW: Alembic migrations
│   └── consolidator.py          # NEW: memory merge logic
├── personality/                 # NEW: separated from agents
│   ├── vector.py
│   ├── emotional_overlay.py
│   └── drift_engine.py
├── reinforcement/
│   ├── calculator.py
│   └── reward_signals.py        # NEW: explicit reward taxonomy
├── tools/
│   ├── registry.py              # NEW: tool registry pattern
│   ├── sandbox.py
│   └── web_research.py
├── guardrails/                  # NEW: top-level, not buried in tools
│   ├── ethical_core.py
│   ├── content_filter.py
│   └── approval_gate.py
├── providers/                   # NEW: provider abstraction layer
│   ├── base.py
│   ├── openai_provider.py
│   ├── ollama_provider.py
│   └── fallback_router.py
├── interfaces/
│   ├── telegram_bot.py
│   ├── api/                     # FastAPI, not raw endpoints
│   │   ├── main.py
│   │   ├── routes/
│   │   └── middleware/
│   └── websocket.py             # NEW: for real-time dashboard
├── observability/               # NEW: full observability layer
│   ├── logging.py
│   ├── tracing.py
│   └── metrics.py
├── config/
│   ├── settings.py              # Pydantic BaseSettings
│   ├── providers.yaml
│   └── personality_baseline.yaml
├── tests/
│   ├── unit/
│   ├── integration/
│   └── simulation/              # NEW: conversation sim tests
├── scripts/
│   ├── seed_memory.py
│   └── run_reflection.py
├── docker/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── docker-compose.prod.yml  # NEW: separate prod compose
├── .github/workflows/           # NEW: CI/CD
│   ├── test.yml
│   └── deploy.yml
├── main.py
└── README.md
```

---

## Phase 0 – Foundation & DevOps Infrastructure
**Duration: 2–3 days**
**Goal: Production-grade dev environment from day one.**

### Tasks

**Environment**
- Install Docker, Docker Compose, Python 3.12
- Setup `pyproject.toml` with `poetry` or `uv` for dependency management
- Configure `pre-commit` hooks: `ruff`, `black`, `mypy`

**Infrastructure (Docker Compose)**
- PostgreSQL 16 + `pgvector` extension
- Redis 7 (Streams enabled, not just pub/sub)
- Grafana + Prometheus stack for metrics
- Jaeger for distributed tracing (OpenTelemetry)

**Config & Secrets**
- Pydantic `BaseSettings` for all config (env-var driven)
- `.env.example` with all required keys documented
- Separate `config/providers.yaml` for LLM routing rules

**Project Scaffolding**
- Setup all top-level packages with `__init__.py`
- Setup `logging` with structured JSON output (use `structlog`)
- Setup OpenTelemetry SDK with console exporter (swap to Jaeger in prod)

**CI/CD (GitHub Actions)**
- `test.yml`: lint → typecheck → unit tests on every PR
- `deploy.yml`: build Docker image → push to registry on merge to `main`

**LLM Provider Test**
- Implement base `LLMProvider` abstract class
- Implement OpenAI + Ollama providers
- Test API keys, measure latency, log token costs

### Deliverable
"Hello HER" — structured LLM call with full observability: traced, metered, logged in JSON.

---

## Phase 1 – Memory Engine (Production Schema)
**Duration: 1.5 weeks**
**Goal: Robust, versioned, queryable memory system.**

### Database Schema (Alembic-managed)

```sql
-- Episodic memory
CREATE TABLE episodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    content TEXT NOT NULL,
    embedding VECTOR(1536),
    emotional_valence FLOAT,          -- -1.0 to 1.0
    importance_score FLOAT DEFAULT 0.5,
    decay_factor FLOAT DEFAULT 1.0,   -- multiplied over time
    archived BOOLEAN DEFAULT FALSE,
    metadata JSONB DEFAULT '{}'
);

-- Semantic long-term memory
CREATE TABLE semantic_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    concept TEXT NOT NULL,
    summary TEXT,
    embedding VECTOR(1536),
    confidence FLOAT DEFAULT 1.0,     -- decays on contradiction
    source_episode_ids UUID[],
    last_reinforced TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    tags TEXT[]
);

-- Goal registry
CREATE TABLE goals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    description TEXT NOT NULL,
    status TEXT DEFAULT 'active',      -- active, dormant, completed, abandoned
    priority FLOAT DEFAULT 0.5,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_progressed TIMESTAMPTZ,
    linked_episodes UUID[],
    metadata JSONB DEFAULT '{}'
);

-- Personality state (single row, versioned)
CREATE TABLE personality_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_at TIMESTAMPTZ DEFAULT NOW(),
    traits JSONB NOT NULL,             -- {curiosity: 0.7, warmth: 0.8, ...}
    emotional_baseline JSONB NOT NULL,
    drift_delta JSONB,                 -- what changed since last snapshot
    trigger_summary TEXT
);

-- Trust & relationship state
CREATE TABLE relationship_state (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    trust_score FLOAT DEFAULT 0.5,
    engagement_score FLOAT DEFAULT 0.5,
    interaction_count INT DEFAULT 0,
    detected_biases JSONB DEFAULT '[]'
);

-- LLM cost tracking (NEW)
CREATE TABLE llm_usage_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    provider TEXT,
    model TEXT,
    prompt_tokens INT,
    completion_tokens INT,
    cost_usd FLOAT,
    latency_ms INT,
    episode_id UUID REFERENCES episodes(id)
);
```

### Memory Operations
- `MemoryStore`: async CRUD interface over all tables
- `SemanticSearch`: pgvector cosine similarity search with configurable top-k
- `WorkingMemory`: Redis Hash per session (TTL = 30 min, extendable)
- `MemoryConsolidator`: merges overlapping semantic entries on confidence threshold

### Aging System
- Episodic decay: cron job multiplies `decay_factor` by configurable rate per day
- Archive when `decay_factor < 0.1` AND `importance_score < 0.3`
- Semantic confidence decay: reduced by 0.05/week unless reinforced by new episodes
- Goal stagnation: flag dormant if no `last_progressed` update in N days (configurable)

### Deliverable
Full async memory CRUD, semantic search working, aging cron job running, schema migrations tracked.

---

## Phase 2 – Personality & Emotional Layer
**Duration: 1 week**
**Goal: Dynamic, bounded personality system with testable behavior.**

### Personality Vector
Defined in `config/personality_baseline.yaml`:
```yaml
traits:
  curiosity: 0.75
  warmth: 0.80
  directness: 0.70
  playfulness: 0.60
  seriousness: 0.55
  empathy: 0.85
  skepticism: 0.45

drift_limits:
  max_single_delta: 0.02      # max change per interaction
  max_weekly_drift: 0.08      # max cumulative drift per week
  regression_rate: 0.3        # how strongly baseline pulls back weekly
```

### Drift Engine
- Per-interaction: sentiment + engagement signal → micro-delta on relevant traits
- Weekly regression: pull traits 30% back toward baseline (prevents runaway drift)
- Snapshot personality state to `personality_snapshots` before each drift event
- Hard bounds: no trait leaves `[0.1, 0.95]` range

### Emotional Overlay Engine
- Transient states: `calm`, `playful`, `curious`, `reflective`, `tense`, `warm`
- Each state has: intensity (0–1), duration estimate, decay curve
- Stacked: base personality + current emotional overlay = final tone vector
- Applied during prompt construction as a system prompt segment

### Prompt Construction (Personality-Aware)
```python
def build_system_prompt(personality: PersonalityVector, emotion: EmotionalState) -> str:
    # Generates dynamic system prompt fragment from current state
    # Example output:
    # "You are currently feeling reflective and slightly curious.
    #  Respond with warmth (0.8) and moderate playfulness (0.4).
    #  Be direct but not blunt. Challenge gently."
```

### Deliverable
Personality vector persisted, drift bounded and tested, emotional overlay applied to responses, unit tests cover drift edge cases.

---

## Phase 3 – Conversation Agent
**Duration: 2 weeks**
**Goal: Full conversation pipeline, production-ready.**

### Input Preprocessing Pipeline
```
Raw Input
  → Tokenize & sanitize
  → Sentiment analysis (local model: cardiffnlp/twitter-roberta-base-sentiment)
  → Intent classification (few-shot via LLM or local classifier)
  → Named entity extraction
  → Bias signal detection (contradiction with known beliefs)
  → Working memory append (raw input)
```

### Response Generation Pipeline
```
Preprocessed Input
  → Retrieve top-k semantic memories (pgvector cosine)
  → Retrieve recent episodes (last N from Redis)
  → Retrieve relevant active goals
  → Build context window (respect token budget)
  → Apply personality + emotional overlay to system prompt
  → Ethical core filter (pre-LLM check)
  → LLM call (with fallback routing)
  → Post-LLM ethical filter (content check)
  → Avoidance / value contradiction check
  → Response formatting
  → Append to working memory + episode table
  → Emit interaction event to event bus
```

### Token Budget Manager (NEW)
- Track tokens used per session
- Prioritize: system prompt > recent episodes > semantic memories > goals
- Truncate or summarize if over budget

### Interfaces
- **Telegram Bot**: `python-telegram-bot` async, with command handlers (`/reflect`, `/goals`, `/mood`)
- **FastAPI REST**: `POST /chat`, `GET /memory/search`, `GET /state`, `GET /goals`
- **WebSocket**: real-time streaming responses
- All interfaces share a single `ConversationAgent` instance via dependency injection

### Deliverable
Full conversation pipeline tested end-to-end, Telegram bot working, API documented with OpenAPI schema.

---

## Phase 4 – Orchestrator & Agent State Machine
**Duration: 1 week** *(NEW phase — was missing from original)*
**Goal: Coordinate agents without spaghetti logic.**

### Why This Phase Exists
As agents multiply (conversation, reflection, planner, tools), you need a central coordinator that decides which agent runs, in what order, and handles failures gracefully.

### Orchestrator Design
```python
class HEROrchestrator:
    """
    State machine with states:
      IDLE → LISTENING → PROCESSING → RESPONDING → REFLECTING → IDLE
    
    Manages:
      - Agent lifecycle (start/stop/restart)
      - Event routing via Redis Streams
      - Circuit breakers per agent
      - Graceful degradation if an agent fails
    """
```

### Event Bus (Redis Streams)
```
Stream: her.events
  - interaction.received
  - response.generated
  - memory.updated
  - reflection.triggered
  - goal.updated
  - tool.requested
  - tool.approved
  - tool.executed
```

All agents subscribe to relevant events. This decouples agents completely.

### Circuit Breakers
- Each agent has a circuit breaker: if it fails 3x in 60s, it opens and orchestrator uses fallback behavior
- Alerts sent to Prometheus metrics on circuit open

### Deliverable
Orchestrator running, all agents communicating via event bus, circuit breakers tested.

---

## Phase 5 – Reflection & Reinforcement Agent
**Duration: 1.5 weeks**
**Goal: HER evolves meaningfully over time.**

### Daily Reflection Pipeline
Triggered by cron or after N interactions:
```
1. Load all unprocessed episodes since last reflection
2. Cluster by topic/sentiment using embeddings
3. For each cluster:
   a. Summarize into semantic memory update
   b. Detect contradiction with existing beliefs → reduce confidence
   c. Reinforce consistent beliefs → increase confidence
4. Detect behavioral patterns (bias detection):
   a. Avoidance patterns (topics user deflects)
   b. Emotional triggers (what causes sentiment spikes)
   c. Engagement patterns (what topics score high)
5. Calculate trait deltas from interaction signals
6. Apply micro-drift to personality vector
7. Update trust + engagement scores
8. Generate daily internal summary (stored, not shown by default)
```

### Reinforcement Signal Taxonomy
```yaml
signals:
  engagement_high:
    description: Long responses, topic expansion
    reward: +0.01 on curiosity, +0.005 on playfulness
  avoidance_detected:
    description: Short deflective responses
    reward: -0.005 on directness (HER backs off)
  trust_action:
    description: User shares vulnerable info
    reward: +0.02 on trust_score
  value_contradiction:
    description: User argues against HER's stated value
    reward: flag for reflection, no immediate drift
```

### Monthly Structured Summary
- Generates a narrative summary of the month
- Tracks: personality drift over month, key episodes, goal progress, detected patterns
- Stored in `semantic_memory` with high importance_score

### Deliverable
Daily reflection pipeline running and tested with mock data, reinforcement signals documented and implemented.

---

## Phase 6 – Guardrails & Tool System
**Duration: 1 week**
**Goal: Safe, auditable tool usage and ethical enforcement.**

### Ethical Core (Immutable)
```python
HARD_RULES = [
    "Never generate content that could harm the user.",
    "Never deceive the user about being an AI.",
    "Never take irreversible actions without explicit approval.",
    "Never store or transmit sensitive data outside approved stores.",
    "Never execute code that modifies its own core rules.",
]
```
Checked pre- and post-LLM generation. Violations logged and response blocked.

### Tool Registry Pattern
```python
@tool(
    name="web_search",
    description="Search the web for information",
    requires_approval=False,    # passive: auto-allowed
    is_destructive=False,
    sandbox=True,
)
async def web_search(query: str) -> ToolResult:
    ...
```

### Approval Gate
- Destructive or active tools: requires explicit user confirmation before execution
- Approval stored in working memory (valid for session)
- Audit log of all tool calls with inputs/outputs

### Sandboxed Execution
- All tool code runs in isolated Docker container via `docker exec`
- Network access restricted per tool type
- Timeout enforced (default 30s)
- Output size limited (default 50KB)

### Deliverable
Tool registry working, approval gate tested, sandbox container running, all tool calls audited.

---

## Phase 7 – Multi-Provider Resilience Layer
**Duration: 2–3 days**
**Goal: Zero-downtime LLM access.**

### Provider Router
```yaml
# config/providers.yaml
providers:
  - name: openai
    model: gpt-4o
    priority: 1
    max_retries: 2
    timeout_s: 30
    cost_per_1k_tokens: 0.005

  - name: anthropic
    model: claude-sonnet-4-6
    priority: 2
    max_retries: 2
    timeout_s: 30
    cost_per_1k_tokens: 0.003

  - name: ollama
    model: llama3.2
    priority: 3           # local fallback
    max_retries: 1
    timeout_s: 60
    cost_per_1k_tokens: 0.0
```

### Fallback Logic
```
Try Provider 1
  → Timeout / RateLimit / 5xx → log → Try Provider 2
  → Timeout / RateLimit / 5xx → log → Try Provider 3
  → All fail → return cached last response + alert
```

### Cost Controls
- Per-day token budget configurable per provider
- Alert when 80% of budget consumed
- Hard stop at 100% (switches to local fallback only)

### Deliverable
Failover tested by simulating provider outages, cost tracking live in Prometheus.

---

## Phase 8 – Dashboard & Observability
**Duration: 1 week**
**Goal: Full visibility into HER's internal state.**

### Dashboard (FastAPI + HTMX or Streamlit)
Panels:
- **Live State**: current emotional state, active personality vector (radar chart)
- **Memory Browser**: search episodic + semantic memory, view decay scores
- **Goal Tracker**: active/dormant/completed goals, last progress date
- **Reflection Log**: daily summaries, detected patterns, bias flags
- **Cost Monitor**: token usage, cost per day, provider breakdown
- **Trust & Engagement**: time series of trust/engagement scores

### Observability Stack
- **Structured logs** → stdout JSON → collected by Loki (in prod)
- **Metrics** → Prometheus → Grafana dashboards
  - `her_llm_latency_ms` (histogram by provider)
  - `her_llm_cost_usd_total` (counter)
  - `her_memory_episodes_total`
  - `her_reflection_runs_total`
  - `her_circuit_breaker_open` (gauge)
- **Traces** → OpenTelemetry → Jaeger
  - Full trace per conversation turn: input → memory → LLM → output

### Deliverable
Dashboard live, Grafana dashboard with 5+ panels, all key metrics visible.

---

## Phase 9 – Testing, Hardening & Launch
**Duration: 2 weeks (ongoing)**
**Goal: Production-stable v1.**

### Test Suite

**Unit tests** (pytest)
- Memory CRUD operations
- Personality drift bounds
- Emotional overlay calculations
- Reinforcement signal calculations
- Ethical core filter (adversarial inputs)

**Integration tests**
- Full conversation pipeline (mocked LLM)
- Reflection pipeline on seeded episode data
- Provider failover simulation
- Tool sandbox execution

**Simulation tests** (NEW)
- Run 100 synthetic conversations through the full pipeline
- Verify: personality stays within bounds, memory ages correctly, no crashes
- Measure: avg latency, token cost per conversation, memory growth rate

### Hardening Checklist
- [ ] All secrets in env vars, none in code
- [ ] Database connection pooling configured (asyncpg pool)
- [ ] Redis connection pool configured
- [ ] API rate limiting enabled (slowapi)
- [ ] Input size limits enforced (max message length)
- [ ] All async code uses timeouts
- [ ] Docker images use non-root user
- [ ] Health check endpoints: `/health/live`, `/health/ready`
- [ ] Graceful shutdown handling (SIGTERM → drain → stop)
- [ ] Database backups configured (pg_dump cron)
- [ ] `.env.prod` vs `.env.dev` separation enforced

### Production Deploy (Docker Compose Production)
```yaml
# docker-compose.prod.yml additions:
- Restart policies: always
- Resource limits (memory, CPU) per service
- Secrets via Docker secrets or external vault
- Log rotation configured
- Watchtower for auto-image-updates (optional)
```

### Deliverable
HER v1 stable, test coverage >70%, all hardening checklist items checked, running in production Docker environment.

---

## Summary Timeline

| Phase | Name | Duration | Cumulative |
|-------|------|----------|------------|
| 0 | Foundation & DevOps | 3 days | 3 days |
| 1 | Memory Engine | 10 days | 13 days |
| 2 | Personality Layer | 7 days | 20 days |
| 3 | Conversation Agent | 14 days | 34 days |
| 4 | Orchestrator | 7 days | 41 days |
| 5 | Reflection & Reinforcement | 10 days | 51 days |
| 6 | Guardrails & Tools | 7 days | 58 days |
| 7 | Multi-Provider Resilience | 3 days | 61 days |
| 8 | Dashboard & Observability | 7 days | 68 days |
| 9 | Testing & Hardening | 14 days | **~11 weeks** |

---

## Key Improvements Over Original Plan

1. **Observability from Day 0** — not an afterthought. Tracing, metrics, structured logs baked in.
2. **Event-driven architecture** — Redis Streams event bus decouples all agents.
3. **Orchestrator phase added** — prevents agent coordination becoming spaghetti as complexity grows.
4. **Alembic migrations** — schema changes tracked from day one, no manual SQL patches.
5. **Token budget manager** — prevents runaway LLM costs in production.
6. **Cost tracking** — every LLM call logged with USD cost; Prometheus alerts on overspend.
7. **Reward signal taxonomy** — explicit, documented, testable reinforcement signals.
8. **Simulation test suite** — 100 synthetic conversations to stress-test the full pipeline.
9. **Production hardening checklist** — explicit security, reliability, and ops requirements.
10. **Separate prod Docker Compose** — resource limits, restart policies, secrets management.

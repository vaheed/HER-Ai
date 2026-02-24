# Architecture

## High-Level Runtime Graph

1. Interface receives interaction (REST/WebSocket/Telegram)
2. Orchestrator passes interaction to `ConversationAgent`
3. Pipeline stages:
   - preprocess input
   - retrieve semantic memory + recent episodes + active goals
   - build personality-aware system prompt
   - enforce token budget and context priority
   - route LLM request through provider fallback
   - enforce post-response guardrails
   - persist episode + usage + events
4. Response returned through calling interface

## Storage and Infrastructure

- PostgreSQL 16 + pgvector
  - episodic memory (`episodes`)
  - semantic memory (`semantic_memory`)
  - goals (`goals`)
  - personality snapshots (`personality_snapshots`)
  - relationship state (`relationship_state`)
  - LLM usage logs (`llm_usage_log`)
- Redis 7
  - session working memory (Hash + TTL)
  - event stream (`her:events`)
- Ollama
  - local chat model execution
  - local embedding model execution

## Service Boundaries

- `her/agents/*`: orchestration, conversation flow, preprocessing, token budgeting, reflection
- `her/memory/*`: persistence models, migrations, CRUD/search logic, lifecycle jobs
- `her/personality/*`: drift, emotion, prompt composition, manager
- `her/providers/*`: LLM providers + fallback router
- `her/embeddings/*`: embedding providers + service abstraction
- `her/interfaces/*`: REST, WebSocket, Telegram
- `her/observability/*`: logs, metrics, tracing

## Reliability Strategies

- Provider fallback on timeout/rate-limit/server/auth errors
- In-memory cache fallback when all LLM providers fail
- Redis working-memory fallback to local in-process storage
- Session-level token budget trimming to prevent context overflow

## Security and Safety Controls

- Ethical hard rules enforced pre and post LLM generation
- Tool execution sandbox boundaries (module-level)
- Secrets expected from environment variables / secret managers
- No credentials committed to repository

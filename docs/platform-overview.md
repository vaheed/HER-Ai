# Platform Overview

## Mission

HER AI is a persistent, evolving AI companion platform designed for local-first deployment with production-grade architecture patterns.

## Core Capabilities

- Persistent memory:
  - Episodic and semantic memory in PostgreSQL + pgvector
  - Working memory in Redis
- Dynamic behavior:
  - Personality drift engine with strict bounds
  - Emotional state transition and decay
- Conversation intelligence:
  - Input preprocessing (intent/sentiment/entities/bias signals)
  - Semantic + episodic + goal retrieval
  - Token budget manager for context-window assembly
- Reliable LLM integration:
  - Multi-provider fallback router (OpenAI, Anthropic, Custom, Ollama)
  - Configurable embedding providers (Ollama, Custom)
- Interfaces:
  - FastAPI REST
  - WebSocket
  - Telegram bot commands and chat runtime
- Observability and operations:
  - Structured logging
  - Prometheus metrics
  - OpenTelemetry tracing

## Phase Completion Snapshot

- Phase 0: Complete
- Phase 1: Complete
- Phase 2: Complete
- Phase 3: Complete

Refer to [roadmap.md](roadmap.md) for detailed checklist status.

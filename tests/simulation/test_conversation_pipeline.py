from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List
from uuid import uuid4

import pytest

from her.agents.conversation import ConversationAgent
from her.agents.orchestrator import AgentOrchestrator
from her.agents.token_budget import TokenBudgetManager
from her.embeddings.base import EmbeddingProvider
from her.embeddings.service import EmbeddingService
from her.memory.types import GoalRecord, SemanticMemoryRecord
from her.models import EmotionalState, Episode, LLMRequest, LLMResponse, PersonalityVector
from her.personality.drift_engine import DriftConfig, DriftEngine
from her.personality.manager import PersonalityManager
from her.providers.base import LLMProvider
from her.providers.fallback_router import FallbackRouter
from her.guardrails.ethical_core import EthicalCore


class DummyProvider(LLMProvider):
    name = "dummy"

    def __init__(self) -> None:
        self.last_request: LLMRequest | None = None

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.last_request = request
        return LLMResponse(
            content="simulated response",
            provider=self.name,
            model="dummy-model",
            prompt_tokens=120,
            completion_tokens=12,
            cost_usd=0.0,
            latency_ms=10,
        )


class FakeEmbeddingProvider(EmbeddingProvider):
    name = "fake"

    async def embed(self, text: str) -> List[float]:
        return [0.01] * 1536


@dataclass
class FakeMemoryStore:
    episodes: List[Episode] = field(default_factory=list)
    usage: List[Dict[str, str]] = field(default_factory=list)
    semantic_records: List[SemanticMemoryRecord] = field(default_factory=list)
    goals: List[GoalRecord] = field(default_factory=list)

    async def add_episode(
        self,
        session_id,
        content: str,
        importance_score: float = 0.5,
        emotional_valence: float = 0.0,
        embedding: List[float] | None = None,
        metadata: Dict[str, str] | None = None,
    ) -> Episode:
        episode = Episode(
            id=uuid4(),
            session_id=session_id,
            timestamp=datetime.utcnow(),
            content=content,
            embedding=embedding,
            emotional_valence=emotional_valence,
            importance_score=importance_score,
            decay_factor=1.0,
            archived=False,
            metadata=metadata or {},
        )
        self.episodes.append(episode)
        return episode

    async def semantic_search(self, query_embedding: List[float], top_k: int, min_confidence: float) -> List[SemanticMemoryRecord]:
        del query_embedding, min_confidence
        return self.semantic_records[:top_k]

    async def list_recent_episodes(self, session_id, limit: int) -> List[Episode]:
        return [episode for episode in self.episodes if episode.session_id == session_id][-limit:]

    async def list_active_goals(self, limit: int) -> List[GoalRecord]:
        return self.goals[:limit]

    async def record_llm_usage(
        self,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        latency_ms: int,
        episode_id,
    ) -> None:
        self.usage.append(
            {
                "provider": provider,
                "model": model,
                "prompt_tokens": str(prompt_tokens),
                "completion_tokens": str(completion_tokens),
                "cost_usd": f"{cost_usd}",
                "latency_ms": str(latency_ms),
                "episode_id": str(episode_id),
            }
        )


@dataclass
class FakeWorkingMemory:
    messages: Dict[str, List[Dict[str, str]]] = field(default_factory=dict)
    events: List[Dict[str, str]] = field(default_factory=list)

    async def append(self, session_id, role: str, content: str) -> None:
        key = str(session_id)
        self.messages.setdefault(key, []).append({"role": role, "content": content})

    async def get(self, session_id) -> List[Dict[str, str]]:
        return list(self.messages.get(str(session_id), []))

    async def emit_event(self, event_type: str, payload: Dict[str, str]) -> None:
        event = {"event": event_type}
        event.update(payload)
        self.events.append(event)


def _baseline_personality() -> PersonalityVector:
    return PersonalityVector(
        curiosity=0.75,
        warmth=0.8,
        directness=0.7,
        playfulness=0.6,
        seriousness=0.55,
        empathy=0.85,
        skepticism=0.45,
    )


def _personality_manager() -> PersonalityManager:
    baseline = _baseline_personality()
    return PersonalityManager(
        baseline_personality=baseline,
        baseline_emotion=EmotionalState(state="calm", intensity=0.2, decay_rate=0.1),
        drift_engine=DriftEngine(baseline, config=DriftConfig()),
        snapshot_store=None,
    )


@pytest.mark.asyncio
async def test_conversation_pipeline_simulation_emits_events_and_records_usage() -> None:
    provider = DummyProvider()
    router = FallbackRouter([provider], timeout_seconds=2)

    semantic_record = SemanticMemoryRecord(
        id=uuid4(),
        concept="response style",
        summary="User prefers concise and practical answers",
        confidence=0.9,
        source_episode_ids=[uuid4()],
        tags=["style"],
    )
    goal = GoalRecord(
        id=uuid4(),
        description="Keep responses concise",
        status="active",
        priority=0.9,
        created_at=datetime.utcnow(),
        last_progressed=None,
        linked_episodes=[],
        metadata={},
    )

    memory_store = FakeMemoryStore(semantic_records=[semantic_record], goals=[goal])
    working_memory = FakeWorkingMemory()
    embedding_service = EmbeddingService(FakeEmbeddingProvider(), dimensions=1536)

    agent = ConversationAgent(
        router=router,
        ethical_core=EthicalCore.default(),
        memory_store=memory_store,  # type: ignore[arg-type]
        working_memory=working_memory,  # type: ignore[arg-type]
        personality_manager=_personality_manager(),
        embedding_service=embedding_service,
        token_budget_manager=TokenBudgetManager(max_input_tokens=500),
        semantic_top_k=5,
        recent_episode_limit=8,
        active_goal_limit=5,
    )
    orchestrator = AgentOrchestrator(agent)

    session_id = uuid4()
    response = await orchestrator.handle_interaction(
        session_id=session_id,
        content="Can you help me plan this migration?",
        trace_id="sim-trace-1",
    )

    assert response.content == "simulated response"
    assert len(memory_store.episodes) == 1
    assert memory_store.episodes[0].metadata["intent"] == "question"
    assert len(memory_store.usage) == 1
    assert provider.last_request is not None
    assert "Input analysis:" in provider.last_request.system_prompt
    event_types = [event["event"] for event in working_memory.events]
    assert "interaction.received" in event_types
    assert "memory.updated" in event_types
    assert "response.generated" in event_types


@pytest.mark.asyncio
async def test_conversation_pipeline_respects_token_budget() -> None:
    provider = DummyProvider()
    router = FallbackRouter([provider], timeout_seconds=2)
    memory_store = FakeMemoryStore()
    working_memory = FakeWorkingMemory()

    session_id = uuid4()
    for idx in range(16):
        await working_memory.append(session_id, "user", f"historic message {idx} " * 16)

    agent = ConversationAgent(
        router=router,
        ethical_core=EthicalCore.default(),
        memory_store=memory_store,  # type: ignore[arg-type]
        working_memory=working_memory,  # type: ignore[arg-type]
        personality_manager=_personality_manager(),
        embedding_service=EmbeddingService(FakeEmbeddingProvider(), dimensions=1536),
        token_budget_manager=TokenBudgetManager(max_input_tokens=180),
        semantic_top_k=3,
        recent_episode_limit=4,
        active_goal_limit=3,
    )
    orchestrator = AgentOrchestrator(agent)

    await orchestrator.handle_interaction(
        session_id=session_id,
        content="Please summarize the last messages quickly.",
        trace_id="sim-trace-2",
    )

    assert provider.last_request is not None
    assert len(provider.last_request.messages) < 17

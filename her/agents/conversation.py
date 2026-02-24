from __future__ import annotations

from typing import Dict, List
from uuid import UUID

from her.agents.preprocessing import ProcessedInput, preprocess_input, processed_summary
from her.agents.token_budget import TokenBudgetManager
from her.embeddings.service import EmbeddingService
from her.guardrails.ethical_core import EthicalCore
from her.memory.store import MemoryStore
from her.memory.types import GoalRecord, SemanticMemoryRecord
from her.memory.working import WorkingMemory
from her.models import Episode, LLMRequest, LLMResponse
from her.observability.logging import get_logger
from her.personality.manager import PersonalityManager
from her.providers.fallback_router import FallbackRouter


class ConversationAgent:
    """Primary conversation agent for user interactions."""

    def __init__(
        self,
        router: FallbackRouter,
        ethical_core: EthicalCore,
        memory_store: MemoryStore,
        working_memory: WorkingMemory,
        personality_manager: PersonalityManager,
        embedding_service: EmbeddingService,
        token_budget_manager: TokenBudgetManager,
        semantic_top_k: int = 5,
        recent_episode_limit: int = 8,
        active_goal_limit: int = 5,
    ) -> None:
        self._router = router
        self._ethical_core = ethical_core
        self._memory_store = memory_store
        self._working = working_memory
        self._personality = personality_manager
        self._embeddings = embedding_service
        self._token_budget = token_budget_manager
        self._semantic_top_k = semantic_top_k
        self._recent_episode_limit = recent_episode_limit
        self._active_goal_limit = active_goal_limit
        self._logger = get_logger("conversation_agent")

    async def respond(self, session_id: UUID, content: str, trace_id: str) -> LLMResponse:
        """Execute conversation pipeline and return LLM response."""

        self._ethical_core.validate_user_content(content)
        processed = await preprocess_input(content)
        await self._emit_event(
            "interaction.received",
            {
                "session_id": str(session_id),
                "content": processed.sanitized_text[:240],
                "trace_id": trace_id,
            },
        )

        embedding = await self._embeddings.embed(processed.sanitized_text)
        semantic_records = await self._retrieve_semantic(embedding)
        recent_episodes = await self._retrieve_recent_episodes(session_id)
        active_goals = await self._retrieve_active_goals()

        episode = await self._persist_episode(session_id, processed, embedding)
        await self._emit_event(
            "memory.updated",
            {
                "episode_id": str(episode.id),
                "type": "episodic",
            },
        )

        await self._working.append(session_id=session_id, role="user", content=processed.sanitized_text)
        history = await self._working.get(session_id)

        base_system_prompt = await self._personality.build_prompt_for_interaction(processed.sanitized_text)
        context_sections = _build_context_sections(processed, semantic_records, recent_episodes, active_goals)
        context_window = self._token_budget.build_window(
            session_id=session_id,
            base_system_prompt=base_system_prompt,
            context_sections=context_sections,
            messages=history,
        )

        self._logger.info(
            "conversation_context_built",
            trace_id=trace_id,
            session_id=str(session_id),
            semantic_hits=len(semantic_records),
            goal_hits=len(active_goals),
            dropped_messages=context_window.dropped_messages,
        )

        request = LLMRequest(
            messages=context_window.messages,
            system_prompt=context_window.system_prompt,
            session_id=session_id,
            trace_id=trace_id,
        )

        response = await self._router.generate(request)
        self._ethical_core.validate_model_content(response.content)

        await self._working.append(session_id=session_id, role="assistant", content=response.content)
        await self._memory_store.record_llm_usage(
            provider=response.provider,
            model=response.model,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            cost_usd=response.cost_usd,
            latency_ms=response.latency_ms,
            episode_id=episode.id,
        )

        await self._emit_event(
            "response.generated",
            {
                "session_id": str(session_id),
                "provider": response.provider,
                "cost_usd": f"{response.cost_usd:.6f}",
            },
        )
        return response

    async def _persist_episode(
        self,
        session_id: UUID,
        processed: ProcessedInput,
        embedding: List[float] | None,
    ) -> Episode:
        metadata: Dict[str, str] = processed_summary(processed)
        return await self._memory_store.add_episode(
            session_id=session_id,
            content=processed.sanitized_text,
            embedding=embedding,
            metadata=metadata,
        )

    async def _retrieve_semantic(self, embedding: List[float] | None) -> List[SemanticMemoryRecord]:
        if embedding is None:
            return []
        try:
            return await self._memory_store.semantic_search(
                query_embedding=embedding,
                top_k=self._semantic_top_k,
                min_confidence=0.2,
            )
        except Exception as exc:
            self._logger.warning("semantic_retrieval_failed", error=str(exc))
            return []

    async def _retrieve_recent_episodes(self, session_id: UUID) -> List[Episode]:
        try:
            return await self._memory_store.list_recent_episodes(
                session_id=session_id,
                limit=self._recent_episode_limit,
            )
        except Exception as exc:
            self._logger.warning("recent_episode_retrieval_failed", error=str(exc))
            return []

    async def _retrieve_active_goals(self) -> List[GoalRecord]:
        try:
            return await self._memory_store.list_active_goals(limit=self._active_goal_limit)
        except Exception as exc:
            self._logger.warning("goal_retrieval_failed", error=str(exc))
            return []

    async def _emit_event(self, event_type: str, payload: Dict[str, str]) -> None:
        try:
            await self._working.emit_event(event_type=event_type, payload=payload)
        except Exception as exc:
            self._logger.warning("event_emit_failed", event_type=event_type, error=str(exc))


def _build_context_sections(
    processed: ProcessedInput,
    semantic_records: List[SemanticMemoryRecord],
    recent_episodes: List[Episode],
    goals: List[GoalRecord],
) -> List[str]:
    summary = processed_summary(processed)
    analysis_section = (
        "Input analysis:\n"
        f"- intent: {summary['intent']}\n"
        f"- sentiment: {summary['sentiment']}\n"
        f"- entities: {summary['entities']}\n"
        f"- bias_signals: {summary['bias']}"
    )

    semantic_lines = [
        f"- {record.concept}: {record.summary} (confidence={record.confidence:.2f})"
        for record in semantic_records[:5]
    ]
    semantic_section = "Relevant semantic memories:\n" + (
        "\n".join(semantic_lines) if semantic_lines else "- none"
    )

    goal_lines = [f"- {goal.description} (priority={goal.priority:.2f})" for goal in goals[:5]]
    goals_section = "Active goals:\n" + ("\n".join(goal_lines) if goal_lines else "- none")

    episode_lines = [f"- {episode.content[:160]}" for episode in recent_episodes[-4:]]
    episode_section = "Recent episode context:\n" + (
        "\n".join(episode_lines) if episode_lines else "- none"
    )

    return [analysis_section, semantic_section, goals_section, episode_section]

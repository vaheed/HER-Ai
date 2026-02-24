from __future__ import annotations

from uuid import UUID

from her.guardrails.ethical_core import EthicalCore
from her.embeddings.service import EmbeddingService
from her.memory.store import MemoryStore
from her.memory.working import WorkingMemory
from her.models import LLMRequest, LLMResponse
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
    ) -> None:
        self._router = router
        self._ethical_core = ethical_core
        self._memory_store = memory_store
        self._working = working_memory
        self._personality = personality_manager
        self._embeddings = embedding_service

    async def respond(self, session_id: UUID, content: str, trace_id: str) -> LLMResponse:
        """Validate, store memory, call provider router, and validate output."""

        self._ethical_core.validate_user_content(content)

        embedding = await self._embeddings.embed(content)
        episode = await self._memory_store.add_episode(
            session_id=session_id,
            content=content,
            embedding=embedding,
        )
        await self._working.append(session_id=session_id, role="user", content=content)
        messages = await self._working.get(session_id)

        request = LLMRequest(
            messages=messages,
            system_prompt=await self._personality.build_prompt_for_interaction(content),
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
        return response

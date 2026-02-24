from __future__ import annotations

from uuid import UUID

from her.guardrails.ethical_core import EthicalCore
from her.memory.episodic import EpisodicMemoryStore
from her.memory.working import WorkingMemory
from her.models import LLMRequest, LLMResponse
from her.providers.fallback_router import FallbackRouter


class ConversationAgent:
    """Primary conversation agent for user interactions."""

    def __init__(
        self,
        router: FallbackRouter,
        ethical_core: EthicalCore,
        episodic_store: EpisodicMemoryStore,
        working_memory: WorkingMemory,
    ) -> None:
        self._router = router
        self._ethical_core = ethical_core
        self._episodic = episodic_store
        self._working = working_memory

    async def respond(self, session_id: UUID, content: str, trace_id: str) -> LLMResponse:
        """Validate, store memory, call provider router, and validate output."""

        self._ethical_core.validate_user_content(content)

        await self._episodic.add_episode(session_id=session_id, content=content)
        await self._working.append(session_id=session_id, role="user", content=content)
        messages = await self._working.get(session_id)

        request = LLMRequest(
            messages=messages,
            system_prompt=(
                "You are HER, an honest AI companion. Be helpful, direct, and safe. "
                "Never claim to be human and never provide harmful instructions."
            ),
            session_id=session_id,
            trace_id=trace_id,
        )

        response = await self._router.generate(request)
        self._ethical_core.validate_model_content(response.content)
        await self._working.append(session_id=session_id, role="assistant", content=response.content)
        return response

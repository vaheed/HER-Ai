from __future__ import annotations

from enum import Enum
from uuid import UUID

from her.agents.conversation import ConversationAgent
from her.models import LLMResponse


class OrchestratorState(str, Enum):
    received = "received"
    generating = "generating"
    completed = "completed"


class AgentOrchestrator:
    """State-machine style coordinator for interaction lifecycle."""

    def __init__(self, conversation_agent: ConversationAgent) -> None:
        self._conversation = conversation_agent

    async def handle_interaction(self, session_id: UUID, content: str, trace_id: str) -> LLMResponse:
        """Run a complete interaction through orchestrated states."""

        _state = OrchestratorState.received
        _state = OrchestratorState.generating
        response = await self._conversation.respond(session_id=session_id, content=content, trace_id=trace_id)
        _state = OrchestratorState.completed
        _ = _state
        return response

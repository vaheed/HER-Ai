from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List
from uuid import uuid4

import pytest

from her.models import EmotionalState, LLMResponse, PersonalityVector
from her.memory.types import GoalRecord
from her.interfaces.telegram_bot import TelegramBotInterface


@dataclass
class FakeMessage:
    text: str = ""
    replies: List[str] = field(default_factory=list)

    async def reply_text(self, value: str) -> None:
        self.replies.append(value)


@dataclass
class FakeChat:
    id: int


@dataclass
class FakeUpdate:
    update_id: int
    effective_message: FakeMessage
    effective_chat: FakeChat


class FakeOrchestrator:
    async def handle_interaction(self, session_id, content: str, trace_id: str) -> LLMResponse:
        del session_id, trace_id
        return LLMResponse(
            content=f"echo: {content}",
            provider="dummy",
            model="dummy-model",
            prompt_tokens=1,
            completion_tokens=1,
            cost_usd=0.0,
            latency_ms=1,
        )


class FakeReflection:
    async def run_daily_reflection(self):
        return PersonalityVector(
            curiosity=0.75,
            warmth=0.8,
            directness=0.7,
            playfulness=0.6,
            seriousness=0.55,
            empathy=0.85,
            skepticism=0.45,
        )


class FakeMemoryStore:
    async def list_active_goals(self, limit: int) -> List[GoalRecord]:
        del limit
        return [
            GoalRecord(
                id=uuid4(),
                description="Keep responses clear",
                status="active",
                priority=0.8,
                created_at=datetime.utcnow(),
                last_progressed=None,
                linked_episodes=[],
                metadata={},
            )
        ]


class FakePersonalityManager:
    @property
    def current_emotion(self) -> EmotionalState:
        return EmotionalState(state="warm", intensity=0.4, decay_rate=0.1)

    @property
    def current_personality(self) -> PersonalityVector:
        return PersonalityVector(
            curiosity=0.75,
            warmth=0.8,
            directness=0.7,
            playfulness=0.6,
            seriousness=0.55,
            empathy=0.85,
            skepticism=0.45,
        )


@pytest.mark.asyncio
async def test_telegram_mood_handler_replies() -> None:
    bot = TelegramBotInterface(
        token="token",
        orchestrator=FakeOrchestrator(),
        reflection_agent=FakeReflection(),
        memory_store=FakeMemoryStore(),
        personality_manager=FakePersonalityManager(),
    )
    update = FakeUpdate(update_id=1, effective_message=FakeMessage(), effective_chat=FakeChat(id=1))

    await bot._handle_mood(update, None)  # type: ignore[arg-type]

    assert update.effective_message.replies
    assert "Current mood state" in update.effective_message.replies[0]


@pytest.mark.asyncio
async def test_telegram_goals_handler_replies() -> None:
    bot = TelegramBotInterface(
        token="token",
        orchestrator=FakeOrchestrator(),
        reflection_agent=FakeReflection(),
        memory_store=FakeMemoryStore(),
        personality_manager=FakePersonalityManager(),
    )
    update = FakeUpdate(update_id=2, effective_message=FakeMessage(), effective_chat=FakeChat(id=2))

    await bot._handle_goals(update, None)  # type: ignore[arg-type]

    assert update.effective_message.replies
    assert "Active goals" in update.effective_message.replies[0]


@pytest.mark.asyncio
async def test_telegram_message_handler_routes_to_orchestrator() -> None:
    bot = TelegramBotInterface(
        token="token",
        orchestrator=FakeOrchestrator(),
        reflection_agent=FakeReflection(),
        memory_store=FakeMemoryStore(),
        personality_manager=FakePersonalityManager(),
    )
    update = FakeUpdate(
        update_id=3,
        effective_message=FakeMessage(text="Hello there"),
        effective_chat=FakeChat(id=3),
    )

    await bot._handle_message(update, None)  # type: ignore[arg-type]

    assert update.effective_message.replies
    assert update.effective_message.replies[0] == "echo: Hello there"

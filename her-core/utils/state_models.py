from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class AgentAction:
    type: str
    command: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentStepEvent:
    event: str
    step_number: int
    action: str
    timestamp: str
    output_preview: str = ""
    verified: bool = False
    execution_ms: float = 0.0

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()


@dataclass
class UserPersonalizationProfile:
    user_id: str
    name: str = ""
    nickname: str = ""
    timezone: str = "UTC"
    preferred_language: str = "en"
    conversation_style: str = "balanced"
    interaction_frequency: str = "normal"
    proactive_opt_out: bool = False
    telegram_user_id: int | None = None
    chat_id: int | None = None


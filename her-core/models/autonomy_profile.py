from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class AutonomyProfile:
    user_id: str
    engagement_score: float = 0.5
    initiative_level: float = 0.5
    last_proactive_at: datetime | None = None
    messages_sent_today: int = 0
    proactive_day: datetime | None = None
    error_count_today: int = 0
    last_user_message_at: datetime | None = None


@dataclass
class EmotionalState:
    user_id: str
    current_mood: str = "calm"
    mood_intensity: float = 0.5
    last_updated: datetime | None = None
    shift_date: datetime | None = None
    shifts_today: int = 0


@dataclass
class ReflectionEntry:
    user_id: str
    date: str
    engagement_trend: str
    initiative_adjustment: float
    notes: str
    confidence: str = "medium"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

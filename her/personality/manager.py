from __future__ import annotations

import asyncio
from typing import Dict, Literal, Optional, Protocol, cast

from her.models import EmotionalState, PersonalityVector
from her.memory.types import PersonalitySnapshotRecord
from her.personality.drift_engine import DriftEngine
from her.personality.emotional_overlay import (
    apply_emotional_overlay,
    decay_emotional_state,
    infer_emotional_state,
)
from her.personality.prompt_builder import build_system_prompt


class PersonalitySnapshotStore(Protocol):
    """Snapshot persistence protocol used by personality manager."""

    async def create_personality_snapshot(
        self,
        traits: Dict[str, float],
        emotional_baseline: Dict[str, float | str | None],
        drift_delta: Optional[Dict[str, float]] = None,
        trigger_summary: Optional[str] = None,
    ) -> None:
        """Persist a personality snapshot."""


class PersonalityManager:
    """Manage dynamic personality drift and emotional state transitions."""

    def __init__(
        self,
        baseline_personality: PersonalityVector,
        baseline_emotion: EmotionalState,
        drift_engine: DriftEngine,
        snapshot_store: Optional[PersonalitySnapshotStore] = None,
    ) -> None:
        self._personality = baseline_personality
        self._emotion = baseline_emotion
        self._drift_engine = drift_engine
        self._snapshot_store = snapshot_store
        self._lock = asyncio.Lock()

    @property
    def current_personality(self) -> PersonalityVector:
        """Return current personality vector."""

        return self._personality

    @property
    def current_emotion(self) -> EmotionalState:
        """Return current emotional state."""

        return self._emotion

    async def build_prompt_for_interaction(self, user_content: str) -> str:
        """Update personality/emotion from interaction and build system prompt."""

        async with self._lock:
            self._emotion = decay_emotional_state(self._emotion)
            next_emotion = infer_emotional_state(user_content, self._emotion)
            deltas = _interaction_deltas(user_content, next_emotion)

            await self._snapshot("interaction", deltas)

            self._personality = self._drift_engine.apply_feedback(self._personality, deltas)
            self._emotion = next_emotion
            tone_vector = apply_emotional_overlay(self._personality, self._emotion)
            return build_system_prompt(tone_vector, self._emotion)

    async def weekly_regression(self) -> PersonalityVector:
        """Apply weekly regression toward baseline with snapshot persistence."""

        async with self._lock:
            await self._snapshot("weekly_regression", {})
            self._personality = self._drift_engine.weekly_regress(self._personality)
            self._emotion = decay_emotional_state(self._emotion, interactions=3)
            return self._personality

    async def restore_from_snapshot(self, snapshot: PersonalitySnapshotRecord) -> None:
        """Restore in-memory personality state from persisted snapshot."""

        async with self._lock:
            restored_state = str(snapshot.emotional_baseline.get("state", "calm"))
            if restored_state not in {"calm", "playful", "curious", "reflective", "tense", "warm"}:
                restored_state = "calm"
            typed_state = cast(
                Literal["calm", "playful", "curious", "reflective", "tense", "warm"], restored_state
            )

            self._personality = PersonalityVector(**snapshot.traits)
            self._emotion = EmotionalState(
                state=typed_state,
                intensity=float(snapshot.emotional_baseline.get("intensity", 0.2) or 0.2),
                decay_rate=float(snapshot.emotional_baseline.get("decay_rate", 0.1) or 0.1),
                triggered_by=(
                    str(snapshot.emotional_baseline["triggered_by"])
                    if snapshot.emotional_baseline.get("triggered_by") is not None
                    else None
                ),
            )

    async def _snapshot(self, trigger: str, deltas: Dict[str, float]) -> None:
        if self._snapshot_store is None:
            return

        emotional_payload: Dict[str, float | str | None] = {
            "state": self._emotion.state,
            "intensity": self._emotion.intensity,
            "decay_rate": self._emotion.decay_rate,
            "triggered_by": self._emotion.triggered_by,
        }
        await self._snapshot_store.create_personality_snapshot(
            traits=self._personality.model_dump(),
            emotional_baseline=emotional_payload,
            drift_delta=deltas,
            trigger_summary=trigger,
        )


def _interaction_deltas(content: str, emotion: EmotionalState) -> Dict[str, float]:
    words = [token for token in content.lower().split() if token]
    engagement = min(1.0, len(words) / 28.0)
    question_weight = min(1.0, content.count("?") / 3.0)
    contains_challenge = any(token in {"why", "prove", "evidence", "sure"} for token in words)

    sentiment = 0.0
    if emotion.state == "warm":
        sentiment = 0.7
    elif emotion.state == "tense":
        sentiment = -0.7

    return {
        "curiosity": round(0.012 * engagement + 0.01 * question_weight, 4),
        "warmth": round(0.01 * sentiment, 4),
        "directness": round(0.008 if len(words) < 12 else -0.004, 4),
        "playfulness": round(0.008 if emotion.state == "playful" else -0.002, 4),
        "seriousness": round(0.009 if emotion.state in {"reflective", "tense"} else -0.003, 4),
        "empathy": round(0.012 if emotion.state in {"warm", "tense"} else 0.002, 4),
        "skepticism": round(0.008 if contains_challenge else -0.002, 4),
    }

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Literal, Mapping

from her.models import EmotionalState, PersonalityVector


@dataclass(frozen=True)
class EmotionalProfile:
    """Trait adjustments applied by an emotional state."""

    trait_deltas: Mapping[str, float]


EMOTIONAL_PROFILES: Dict[str, EmotionalProfile] = {
    "calm": EmotionalProfile(trait_deltas={"seriousness": 0.04, "playfulness": -0.03}),
    "playful": EmotionalProfile(trait_deltas={"playfulness": 0.08, "seriousness": -0.05}),
    "curious": EmotionalProfile(trait_deltas={"curiosity": 0.08, "skepticism": 0.03}),
    "reflective": EmotionalProfile(trait_deltas={"seriousness": 0.07, "empathy": 0.03}),
    "tense": EmotionalProfile(trait_deltas={"warmth": -0.06, "directness": 0.06}),
    "warm": EmotionalProfile(trait_deltas={"warmth": 0.08, "empathy": 0.07}),
}


POSITIVE_TOKENS = {
    "thanks",
    "great",
    "awesome",
    "love",
    "good",
    "nice",
    "amazing",
    "helpful",
}
NEGATIVE_TOKENS = {
    "angry",
    "upset",
    "hate",
    "bad",
    "annoyed",
    "frustrated",
    "sad",
    "stressed",
}


def infer_emotional_state(text: str, current: EmotionalState) -> EmotionalState:
    """Infer the next emotional state from interaction signals."""

    words = _tokenize(text)
    positive_hits = sum(1 for word in words if word in POSITIVE_TOKENS)
    negative_hits = sum(1 for word in words if word in NEGATIVE_TOKENS)
    engagement = min(1.0, len(words) / 36.0)
    question_count = text.count("?")

    next_state: Literal["calm", "playful", "curious", "reflective", "tense", "warm"]
    if negative_hits > positive_hits and negative_hits > 0:
        next_state = "tense"
    elif question_count > 0 and engagement >= 0.25:
        next_state = "curious"
    elif positive_hits > negative_hits and positive_hits > 0:
        next_state = "warm"
    elif engagement > 0.7:
        next_state = "reflective"
    elif any(word in {"joke", "fun", "haha", "lol"} for word in words):
        next_state = "playful"
    else:
        next_state = "calm"

    signal_strength = abs(positive_hits - negative_hits) + (0.5 if question_count > 0 else 0.0) + engagement
    target_intensity = min(1.0, 0.2 + signal_strength * 0.35)
    decayed = decay_emotional_state(current)

    blended_intensity = (decayed.intensity * 0.55) + (target_intensity * 0.45)
    if next_state == "calm":
        blended_intensity = min(blended_intensity, 0.35)

    return EmotionalState(
        state=next_state,
        intensity=round(max(0.0, min(1.0, blended_intensity)), 3),
        decay_rate=current.decay_rate,
        triggered_by=next_state if next_state != "calm" else None,
    )


def decay_emotional_state(state: EmotionalState, interactions: int = 1) -> EmotionalState:
    """Decay emotion intensity by interaction count using exponential decay."""

    remaining = state.intensity * ((1.0 - state.decay_rate) ** max(0, interactions))
    if remaining < 0.12:
        return EmotionalState(state="calm", intensity=round(max(0.0, remaining), 3), decay_rate=state.decay_rate)

    return EmotionalState(
        state=state.state,
        intensity=round(max(0.0, min(1.0, remaining)), 3),
        decay_rate=state.decay_rate,
        triggered_by=state.triggered_by,
    )


def apply_emotional_overlay(personality: PersonalityVector, emotional_state: EmotionalState) -> PersonalityVector:
    """Return tone vector after applying emotional overlay to personality traits."""

    profile = EMOTIONAL_PROFILES.get(emotional_state.state, EMOTIONAL_PROFILES["calm"])
    baseline = personality.model_dump()
    adjusted: Dict[str, float] = {}

    for trait, value in baseline.items():
        delta = profile.trait_deltas.get(trait, 0.0) * emotional_state.intensity
        adjusted_value = max(0.1, min(0.95, value + delta))
        adjusted[trait] = round(adjusted_value, 4)

    return PersonalityVector(**adjusted)


def _tokenize(text: str) -> list[str]:
    normalized = text.lower()
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in normalized)
    return [token for token in cleaned.split() if token]

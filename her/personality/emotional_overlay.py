from __future__ import annotations

from her.models import EmotionalState


def apply_emotional_overlay(text: str, emotional_state: EmotionalState) -> str:
    """Modulate response style with a lightweight emotional overlay."""

    prefix_map = {
        "calm": "",
        "playful": "Playful tone: ",
        "curious": "Curious tone: ",
        "reflective": "Reflective tone: ",
        "tense": "Focused tone: ",
        "warm": "Warm tone: ",
    }
    prefix = prefix_map.get(emotional_state.state, "")
    return f"{prefix}{text}" if prefix else text

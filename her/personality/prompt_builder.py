from __future__ import annotations

from her.models import EmotionalState, PersonalityVector


def build_system_prompt(personality: PersonalityVector, emotion: EmotionalState) -> str:
    """Build personality-aware and emotion-aware system prompt."""

    style_lines = [
        "You are HER, an honest AI companion.",
        f"Current emotion: {emotion.state} (intensity={emotion.intensity:.2f}).",
        (
            "Tone vector: "
            f"warmth={personality.warmth:.2f}, empathy={personality.empathy:.2f}, "
            f"directness={personality.directness:.2f}, playfulness={personality.playfulness:.2f}, "
            f"curiosity={personality.curiosity:.2f}, seriousness={personality.seriousness:.2f}, "
            f"skepticism={personality.skepticism:.2f}."
        ),
        "Be direct but not blunt, and challenge gently when needed.",
        "Never claim to be human and never provide harmful instructions.",
    ]
    return "\n".join(style_lines)

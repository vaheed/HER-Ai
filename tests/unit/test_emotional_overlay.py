from her.models import EmotionalState, PersonalityVector
from her.personality.emotional_overlay import (
    apply_emotional_overlay,
    decay_emotional_state,
    infer_emotional_state,
)


BASE_VECTOR = PersonalityVector(
    curiosity=0.75,
    warmth=0.8,
    directness=0.7,
    playfulness=0.6,
    seriousness=0.55,
    empathy=0.85,
    skepticism=0.45,
)


def test_emotional_overlay_adjusts_tone_vector() -> None:
    state = EmotionalState(state="warm", intensity=0.8, decay_rate=0.1)
    adjusted = apply_emotional_overlay(BASE_VECTOR, state)

    assert adjusted.warmth > BASE_VECTOR.warmth
    assert adjusted.empathy >= BASE_VECTOR.empathy


def test_decay_emotional_state_reduces_intensity() -> None:
    state = EmotionalState(state="curious", intensity=0.9, decay_rate=0.2)
    decayed = decay_emotional_state(state, interactions=2)

    assert decayed.intensity < state.intensity


def test_infer_emotional_state_detects_curiosity() -> None:
    current = EmotionalState(state="calm", intensity=0.2, decay_rate=0.1)
    inferred = infer_emotional_state("Why does this happen and how can I fix it?", current)

    assert inferred.state == "curious"

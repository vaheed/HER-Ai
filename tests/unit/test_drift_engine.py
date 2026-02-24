from her.models import PersonalityVector
from her.personality.drift_engine import DriftEngine


def build_vector() -> PersonalityVector:
    return PersonalityVector(
        curiosity=0.75,
        warmth=0.8,
        directness=0.7,
        playfulness=0.6,
        seriousness=0.55,
        empathy=0.85,
        skepticism=0.45,
    )


def test_drift_respects_single_step_and_bounds() -> None:
    baseline = build_vector()
    engine = DriftEngine(baseline)
    updated = engine.apply_feedback(baseline, {"curiosity": 0.2, "warmth": -0.2})

    assert updated.curiosity == 0.77
    assert updated.warmth == 0.78
    assert 0.1 <= updated.curiosity <= 0.95
    assert 0.1 <= updated.warmth <= 0.95

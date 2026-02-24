from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import pytest

from her.models import EmotionalState, PersonalityVector
from her.memory.types import PersonalitySnapshotRecord
from her.personality.drift_engine import DriftConfig, DriftEngine
from her.personality.manager import PersonalityManager


@dataclass
class SnapshotCall:
    traits: Dict[str, float]
    emotional_baseline: Dict[str, float | str | None]
    drift_delta: Optional[Dict[str, float]]
    trigger_summary: Optional[str]


@dataclass
class FakeSnapshotStore:
    calls: List[SnapshotCall] = field(default_factory=list)

    async def create_personality_snapshot(
        self,
        traits: Dict[str, float],
        emotional_baseline: Dict[str, float | str | None],
        drift_delta: Optional[Dict[str, float]] = None,
        trigger_summary: Optional[str] = None,
    ) -> None:
        self.calls.append(
            SnapshotCall(
                traits=traits,
                emotional_baseline=emotional_baseline,
                drift_delta=drift_delta,
                trigger_summary=trigger_summary,
            )
        )


def _baseline() -> PersonalityVector:
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
async def test_personality_manager_builds_prompt_and_snapshots() -> None:
    baseline = _baseline()
    snapshot_store = FakeSnapshotStore()
    manager = PersonalityManager(
        baseline_personality=baseline,
        baseline_emotion=EmotionalState(state="calm", intensity=0.2, decay_rate=0.1),
        drift_engine=DriftEngine(baseline, config=DriftConfig()),
        snapshot_store=snapshot_store,
    )

    prompt = await manager.build_prompt_for_interaction("Why is this failing? I need help.")

    assert "Current emotion:" in prompt
    assert "Tone vector:" in prompt
    assert len(snapshot_store.calls) == 1
    assert snapshot_store.calls[0].trigger_summary == "interaction"


@pytest.mark.asyncio
async def test_personality_manager_weekly_regression_creates_snapshot() -> None:
    baseline = _baseline()
    snapshot_store = FakeSnapshotStore()
    manager = PersonalityManager(
        baseline_personality=baseline,
        baseline_emotion=EmotionalState(state="warm", intensity=0.6, decay_rate=0.1),
        drift_engine=DriftEngine(baseline, config=DriftConfig()),
        snapshot_store=snapshot_store,
    )

    await manager.build_prompt_for_interaction("This is awesome, thanks!")
    updated = await manager.weekly_regression()

    assert isinstance(updated, PersonalityVector)
    assert len(snapshot_store.calls) == 2
    assert snapshot_store.calls[-1].trigger_summary == "weekly_regression"


@pytest.mark.asyncio
async def test_personality_manager_restore_from_snapshot() -> None:
    baseline = _baseline()
    manager = PersonalityManager(
        baseline_personality=baseline,
        baseline_emotion=EmotionalState(state="calm", intensity=0.2, decay_rate=0.1),
        drift_engine=DriftEngine(baseline, config=DriftConfig()),
        snapshot_store=None,
    )
    snapshot = PersonalitySnapshotRecord(
        snapshot_at=datetime.utcnow(),
        traits={
            "curiosity": 0.81,
            "warmth": 0.74,
            "directness": 0.68,
            "playfulness": 0.57,
            "seriousness": 0.6,
            "empathy": 0.88,
            "skepticism": 0.5,
        },
        emotional_baseline={"state": "reflective", "intensity": 0.5, "decay_rate": 0.1, "triggered_by": None},
        drift_delta={"curiosity": 0.02},
        trigger_summary="interaction",
    )

    await manager.restore_from_snapshot(snapshot)

    assert manager.current_personality.curiosity == 0.81
    assert manager.current_emotion.state == "reflective"

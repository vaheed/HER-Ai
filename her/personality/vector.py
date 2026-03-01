from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml  # type: ignore[import-untyped]

from her.models import EmotionalState, PersonalityVector
from her.personality.drift_engine import DriftConfig


def load_personality_baseline(config_path: Path) -> PersonalityVector:
    """Load the personality baseline vector from YAML."""

    with config_path.open("r", encoding="utf-8") as handle:
        payload: Dict[str, Any] = yaml.safe_load(handle)
    return PersonalityVector(**payload["traits"])


def load_emotional_baseline(config_path: Path) -> EmotionalState:
    """Load emotional baseline state from YAML."""

    with config_path.open("r", encoding="utf-8") as handle:
        payload: Dict[str, Any] = yaml.safe_load(handle)
    return EmotionalState(**payload["emotion"])


def load_drift_config(config_path: Path) -> DriftConfig:
    """Load drift configuration from personality baseline YAML."""

    with config_path.open("r", encoding="utf-8") as handle:
        payload: Dict[str, Any] = yaml.safe_load(handle)
    drift_limits = payload.get("drift_limits", {})
    return DriftConfig(**drift_limits)

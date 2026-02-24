from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from her.models import PersonalityVector


@dataclass
class DriftConfig:
    max_single_delta: float = 0.02
    max_weekly_drift: float = 0.08
    regression_rate: float = 0.3
    lower_bound: float = 0.1
    upper_bound: float = 0.95


class DriftEngine:
    """Apply bounded personality drift from interaction feedback."""

    def __init__(self, baseline: PersonalityVector, config: DriftConfig | None = None) -> None:
        self._baseline = baseline
        self._config = config or DriftConfig()
        self._weekly_accumulator: Dict[str, float] = {k: 0.0 for k in baseline.model_dump().keys()}

    def apply_feedback(self, current: PersonalityVector, deltas: Dict[str, float]) -> PersonalityVector:
        """Apply bounded deltas and return updated personality vector."""

        current_map = current.model_dump()
        next_map: Dict[str, float] = {}

        for trait, value in current_map.items():
            delta = deltas.get(trait, 0.0)
            delta = max(-self._config.max_single_delta, min(self._config.max_single_delta, delta))

            weekly = self._weekly_accumulator[trait] + delta
            weekly = max(-self._config.max_weekly_drift, min(self._config.max_weekly_drift, weekly))
            delta = weekly - self._weekly_accumulator[trait]
            self._weekly_accumulator[trait] = weekly

            proposed = value + delta
            bounded = max(self._config.lower_bound, min(self._config.upper_bound, proposed))
            next_map[trait] = round(bounded, 4)

        return PersonalityVector(**next_map)

    def weekly_regress(self, current: PersonalityVector) -> PersonalityVector:
        """Pull personality toward baseline and decay weekly accumulator."""

        current_map = current.model_dump()
        base_map = self._baseline.model_dump()
        next_map: Dict[str, float] = {}

        for trait, value in current_map.items():
            baseline_value = base_map[trait]
            adjustment = (baseline_value - value) * self._config.regression_rate
            moved = value + adjustment
            bounded = max(self._config.lower_bound, min(self._config.upper_bound, moved))
            next_map[trait] = round(bounded, 4)
            self._weekly_accumulator[trait] *= 1 - self._config.regression_rate

        return PersonalityVector(**next_map)

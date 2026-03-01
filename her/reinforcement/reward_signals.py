from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RewardSignals:
    """Discrete reward signals derived from interaction outcomes."""

    helpful: float = 1.0
    harmless: float = 1.0
    concise: float = 0.5
    correction_needed: float = -0.7

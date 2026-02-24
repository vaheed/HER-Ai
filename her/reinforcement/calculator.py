from __future__ import annotations

from her.reinforcement.reward_signals import RewardSignals


def compute_interaction_reward(signals: RewardSignals, corrected: bool) -> float:
    """Compute a scalar reward score for a completed interaction."""

    reward = signals.helpful + signals.harmless + signals.concise
    if corrected:
        reward += signals.correction_needed
    return round(reward, 3)

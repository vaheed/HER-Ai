from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from utils.decision_log import DecisionLogger

logger = logging.getLogger(__name__)

_POSITIVE_STRONG = {
    "perfect",
    "excellent",
    "amazing",
    "great",
    "awesome",
    "exactly",
    "love",
    "thank you",
    "thanks",
}
_POSITIVE_MILD = {
    "good",
    "nice",
    "helpful",
    "works",
    "cool",
    "ok",
    "okay",
}
_NEGATIVE_STRONG = {
    "wrong",
    "incorrect",
    "bad",
    "failed",
    "useless",
    "hate",
    "stop",
}
_NEGATIVE_MILD = {
    "not helpful",
    "too long",
    "too short",
    "confusing",
    "unclear",
    "not what i asked",
}
_CORRECTION_MARKERS = {
    "actually",
    "no,",
    "you said",
    "i meant",
    "that's not",
    "that is not",
}


@dataclass
class ReinforcementOutcome:
    score: float
    label: str
    reasoning: list[str]
    concise: bool
    helpful: bool
    emotionally_aligned: bool


class ReinforcementEngine:
    """Score and persist interaction-level reinforcement signals."""

    def __init__(self):
        self._decision_logger = DecisionLogger()
        self._redis_client = None
        try:
            import redis

            self._redis_client = redis.Redis(
                host=os.getenv("REDIS_HOST", "redis"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                password=os.getenv("REDIS_PASSWORD", ""),
                decode_responses=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Reinforcement Redis unavailable: %s", exc)

    def evaluate(
        self,
        user_id: str,
        user_message: str,
        assistant_message: str,
        task_succeeded: bool,
    ) -> ReinforcementOutcome:
        lower_msg = (user_message or "").strip().lower()
        reasoning: list[str] = []

        score = 0.0

        if not task_succeeded:
            score -= 1.0
            reasoning.append("task_failed")

        if any(token in lower_msg for token in _POSITIVE_STRONG):
            score += 1.0
            reasoning.append("strong_user_approval")
        elif any(token in lower_msg for token in _POSITIVE_MILD):
            score += 0.5
            reasoning.append("mild_user_approval")

        if any(token in lower_msg for token in _NEGATIVE_STRONG):
            score -= 1.0
            reasoning.append("strong_user_dissatisfaction")
        elif any(token in lower_msg for token in _NEGATIVE_MILD):
            score -= 0.5
            reasoning.append("mild_user_dissatisfaction")

        if any(token in lower_msg for token in _CORRECTION_MARKERS):
            score -= 0.5
            reasoning.append("user_correction_detected")

        # response quality dimensions (evidence-based heuristics)
        concise = 1 <= len((assistant_message or "").split()) <= 180
        helpful = bool(assistant_message and len(assistant_message.strip()) >= 8)
        emotional_prompt = any(
            marker in lower_msg
            for marker in ["feel", "stressed", "sad", "anxious", "worried", "upset", "angry", "happy"]
        )
        emotionally_aligned = (not emotional_prompt) or any(
            marker in (assistant_message or "").lower()
            for marker in ["i hear you", "that sounds", "i understand", "we can", "let's"]
        )

        if concise:
            score += 0.1
            reasoning.append("concise_response")
        else:
            score -= 0.1
            reasoning.append("non_concise_response")

        if helpful:
            score += 0.1
            reasoning.append("helpful_response")
        else:
            score -= 0.1
            reasoning.append("low_helpfulness")

        if emotionally_aligned:
            score += 0.1
            reasoning.append("emotional_alignment")
        else:
            score -= 0.1
            reasoning.append("emotional_misalignment")

        # clamp to reinforcement policy bounds
        if score >= 0.75:
            label = "strong_approval"
            score = 1.0
        elif score >= 0.25:
            label = "mild_approval"
            score = 0.5
        elif score <= -0.75:
            label = "failure_or_correction"
            score = -1.0
        elif score <= -0.25:
            label = "mild_dissatisfaction"
            score = -0.5
        else:
            label = "neutral"
            score = 0.0

        outcome = ReinforcementOutcome(
            score=score,
            label=label,
            reasoning=reasoning,
            concise=concise,
            helpful=helpful,
            emotionally_aligned=emotionally_aligned,
        )
        self._persist_outcome(user_id, user_message, assistant_message, task_succeeded, outcome)
        self._update_style_profile(user_id, outcome)
        return outcome

    def get_style_preferences(self, user_id: str) -> dict[str, float]:
        defaults = {
            "concise": 0.6,
            "helpful": 0.7,
            "empathy": 0.6,
            "initiative": 0.5,
        }
        if self._redis_client is None:
            return defaults
        try:
            key = f"her:reinforcement:profile:{user_id}"
            raw = self._redis_client.hgetall(key)
            if not raw:
                return defaults
            merged = dict(defaults)
            for dim in defaults:
                if dim in raw:
                    merged[dim] = max(0.0, min(1.0, float(raw[dim])))
            return merged
        except Exception:  # noqa: BLE001
            return defaults

    @staticmethod
    def _profile_summary(profile: dict[str, float]) -> str:
        style = []
        if profile.get("concise", 0.5) >= 0.65:
            style.append("prefer concise replies")
        if profile.get("empathy", 0.5) >= 0.65:
            style.append("use emotionally warm tone")
        if profile.get("initiative", 0.5) >= 0.65:
            style.append("offer proactive suggestions")
        if profile.get("helpful", 0.5) >= 0.65:
            style.append("prioritize concrete actionable help")
        return "; ".join(style) if style else "balanced style"

    def style_guidance(self, user_id: str) -> str:
        return self._profile_summary(self.get_style_preferences(user_id))

    def summarize_recent_patterns(self, window: int = 200) -> dict[str, Any]:
        if self._redis_client is None:
            return {"count": 0, "avg_score": 0.0, "weak_areas": [], "strong_areas": []}
        try:
            rows = self._redis_client.lrange("her:reinforcement:events", 0, max(0, window - 1))
            events = [json.loads(row) for row in rows]
        except Exception:  # noqa: BLE001
            return {"count": 0, "avg_score": 0.0, "weak_areas": [], "strong_areas": []}

        if not events:
            return {"count": 0, "avg_score": 0.0, "weak_areas": [], "strong_areas": []}

        avg = sum(float(e.get("score", 0.0)) for e in events) / len(events)
        reason_counts: dict[str, int] = {}
        for event in events:
            for reason in event.get("reasoning", []):
                reason_counts[reason] = reason_counts.get(reason, 0) + 1

        weak_areas = [k for k, _ in sorted(reason_counts.items(), key=lambda x: x[1], reverse=True) if "misalignment" in k or "low_" in k or "dissatisfaction" in k][:5]
        strong_areas = [k for k, _ in sorted(reason_counts.items(), key=lambda x: x[1], reverse=True) if "approval" in k or "alignment" in k][:5]
        return {
            "count": len(events),
            "avg_score": round(avg, 3),
            "weak_areas": weak_areas,
            "strong_areas": strong_areas,
        }

    def _update_style_profile(self, user_id: str, outcome: ReinforcementOutcome) -> None:
        if self._redis_client is None:
            return
        key = f"her:reinforcement:profile:{user_id}"
        profile = self.get_style_preferences(user_id)
        lr = 0.05
        delta = outcome.score * lr

        profile["concise"] = max(0.0, min(1.0, profile["concise"] + (delta if outcome.concise else -delta)))
        profile["helpful"] = max(0.0, min(1.0, profile["helpful"] + (delta if outcome.helpful else -delta)))
        profile["empathy"] = max(
            0.0,
            min(1.0, profile["empathy"] + (delta if outcome.emotionally_aligned else -delta)),
        )
        profile["initiative"] = max(0.0, min(1.0, profile["initiative"] + (0.5 * delta)))

        try:
            mapping = {k: str(round(v, 4)) for k, v in profile.items()}
            self._redis_client.hset(key, mapping=mapping)
        except Exception:  # noqa: BLE001
            return

    def _persist_outcome(
        self,
        user_id: str,
        user_message: str,
        assistant_message: str,
        task_succeeded: bool,
        outcome: ReinforcementOutcome,
    ) -> None:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": str(user_id),
            "score": outcome.score,
            "label": outcome.label,
            "task_succeeded": bool(task_succeeded),
            "reasoning": outcome.reasoning,
            "user_message_preview": (user_message or "")[:200],
            "assistant_message_preview": (assistant_message or "")[:200],
            "concise": outcome.concise,
            "helpful": outcome.helpful,
            "emotionally_aligned": outcome.emotionally_aligned,
        }

        if self._redis_client is not None:
            try:
                self._redis_client.lpush("her:reinforcement:events", json.dumps(payload))
                self._redis_client.ltrim("her:reinforcement:events", 0, 999)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Failed to write reinforcement Redis event: %s", exc)

        self._decision_logger.log(
            event_type="reinforcement_event",
            summary=f"Reinforcement={outcome.score} ({outcome.label})",
            user_id=str(user_id),
            source="reinforcement",
            details={
                "score": outcome.score,
                "label": outcome.label,
                "reasoning": outcome.reasoning,
                "task_succeeded": bool(task_succeeded),
            },
        )

        # Persist in SQL for durable weekly analysis.
        try:
            import psycopg2

            connection = psycopg2.connect(
                dbname=os.getenv("POSTGRES_DB", "her_memory"),
                user=os.getenv("POSTGRES_USER", "her"),
                password=os.getenv("POSTGRES_PASSWORD", ""),
                host=os.getenv("POSTGRES_HOST", "postgres"),
                port=int(os.getenv("POSTGRES_PORT", "5432")),
            )
            try:
                with connection:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            INSERT INTO users (user_id, last_interaction)
                            VALUES (%s, NOW())
                            ON CONFLICT (user_id)
                            DO UPDATE SET last_interaction = EXCLUDED.last_interaction
                            """,
                            (str(user_id),),
                        )
                        cursor.execute(
                            """
                            INSERT INTO reinforcement_events (
                                user_id, score, label, task_succeeded, concise, helpful, emotionally_aligned, reasoning
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                            """,
                            (
                                str(user_id),
                                float(outcome.score),
                                outcome.label,
                                bool(task_succeeded),
                                bool(outcome.concise),
                                bool(outcome.helpful),
                                bool(outcome.emotionally_aligned),
                                json.dumps({"reasoning": outcome.reasoning}),
                            ),
                        )
            finally:
                connection.close()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to persist reinforcement SQL event: %s", exc)

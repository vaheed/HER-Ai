import logging
import os
import json
from pathlib import Path

import psycopg2
from crewai import Agent

from agents.base_agent import BaseAgent
from utils.decision_log import DecisionLogger


class PersonalityAgent(BaseAgent):
    def __init__(self, config_path: Path, personality_path: Path) -> None:
        super().__init__(config_path)
        self._config = self._config.get("personality_agent", {})
        self._personality = self._load_config(personality_path)
        self._defaults = dict(self._personality.get("default_traits", {}))
        self._traits_by_user: dict[str, dict[str, int]] = {}
        self._logger = logging.getLogger(__name__)
        self._decision_logger = DecisionLogger()

    def build(self) -> Agent:
        return self.create_agent(
            role=self._config.get("role", "Personality Manager"),
            goal=self._config.get("goal", "Track and evolve personality traits safely"),
            backstory=self._config.get("backstory", "You maintain HER's personality traits over time while enforcing safe and consistent emotional boundaries."),
        )

    def get_current_traits(self, user_id: str) -> dict[str, int]:
        key = str(user_id)
        if key not in self._traits_by_user:
            self._traits_by_user[key] = self._load_latest_traits(key)
        return dict(self._traits_by_user[key])

    def adjust_trait(self, user_id: str, trait_name: str, delta: int) -> dict[str, int]:
        key = str(user_id)
        bounds = self._config.get("boundaries", {"min": 20, "max": 95})
        traits = self.get_current_traits(key)
        current = int(traits.get(trait_name, bounds.get("min", 20)))
        updated = max(bounds.get("min", 20), min(bounds.get("max", 95), current + delta))
        traits[trait_name] = updated
        self.save_version(key, traits, notes=f"adjust {trait_name} by {delta}")
        self._decision_logger.log(
            event_type="personality_adjustment",
            summary=f"Adjusted trait '{trait_name}' by {delta}",
            user_id=key,
            source="personality_agent",
            details={"trait": trait_name, "delta": delta, "new_value": updated},
        )
        return dict(traits)

    def save_version(self, user_id: str, traits: dict[str, int], notes: str | None = None) -> dict[str, int]:
        key = str(user_id)
        cleaned = {str(k): int(v) for k, v in traits.items()}
        self._traits_by_user[key] = cleaned
        self._persist_traits(key, cleaned, notes=notes)
        return dict(cleaned)

    def _load_latest_traits(self, user_id: str) -> dict[str, int]:
        try:
            with self._db_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT warmth, curiosity, assertiveness, humor, emotional_depth
                        FROM personality_states
                        WHERE user_id = %s
                        ORDER BY created_at DESC
                        LIMIT 1
                        """,
                        (user_id,),
                    )
                    row = cursor.fetchone()
            if not row:
                return dict(self._defaults)
            keys = ["warmth", "curiosity", "assertiveness", "humor", "emotional_depth"]
            loaded = dict(self._defaults)
            for idx, key in enumerate(keys):
                if row[idx] is not None:
                    loaded[key] = int(row[idx])
            return loaded
        except Exception as exc:  # noqa: BLE001
            self._logger.debug("Personality DB load failed for %s: %s", user_id, exc)
            return dict(self._defaults)

    def _persist_traits(self, user_id: str, traits: dict[str, int], notes: str | None = None) -> None:
        try:
            with self._db_connection() as connection:
                with connection:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            INSERT INTO users (user_id, last_interaction)
                            VALUES (%s, NOW())
                            ON CONFLICT (user_id)
                            DO UPDATE SET last_interaction = EXCLUDED.last_interaction
                            """,
                            (user_id,),
                        )
                        cursor.execute(
                            """
                            SELECT COALESCE(MAX(version), 0) + 1
                            FROM personality_states
                            WHERE user_id = %s
                            """,
                            (user_id,),
                        )
                        version = int(cursor.fetchone()[0])
                        cursor.execute(
                            """
                            INSERT INTO personality_states (
                                user_id, warmth, curiosity, assertiveness, humor, emotional_depth, version, changes
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                            """,
                            (
                                user_id,
                                traits.get("warmth"),
                                traits.get("curiosity"),
                                traits.get("assertiveness"),
                                traits.get("humor"),
                                traits.get("emotional_depth"),
                                version,
                                json.dumps({"notes": notes or ""}),
                            ),
                        )
        except Exception as exc:  # noqa: BLE001
            self._logger.debug("Personality DB persist failed for %s: %s", user_id, exc)

    @staticmethod
    def _db_connection():
        return psycopg2.connect(
            dbname=os.getenv("POSTGRES_DB", "her_memory"),
            user=os.getenv("POSTGRES_USER", "her"),
            password=os.getenv("POSTGRES_PASSWORD", ""),
            host=os.getenv("POSTGRES_HOST", "postgres"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
        )

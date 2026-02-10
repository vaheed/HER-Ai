from pathlib import Path

from crewai import Agent

from agents.base_agent import BaseAgent


class PersonalityAgent(BaseAgent):
    def __init__(self, config_path: Path, personality_path: Path) -> None:
        super().__init__(config_path)
        self._config = self._config.get("personality_agent", {})
        self._personality = self._load_config(personality_path)
        self._traits = self._personality.get("default_traits", {})

    def build(self) -> Agent:
        return self.create_agent(
            role=self._config.get("role", "Personality Manager"),
            goal=self._config.get("goal", "Track and evolve personality traits safely"),
            backstory=self._config.get("backstory", "You maintain HER's personality traits over time while enforcing safe and consistent emotional boundaries."),
        )

    def get_current_traits(self, user_id: str) -> dict[str, int]:
        return dict(self._traits)

    def adjust_trait(self, user_id: str, trait_name: str, delta: int) -> dict[str, int]:
        bounds = self._config.get("boundaries", {"min": 20, "max": 95})
        current = self._traits.get(trait_name, bounds.get("min", 20))
        updated = max(bounds.get("min", 20), min(bounds.get("max", 95), current + delta))
        self._traits[trait_name] = updated
        return dict(self._traits)

    def save_version(self, user_id: str, traits: dict[str, int], notes: str | None = None) -> dict[str, int]:
        self._traits = dict(traits)
        return self._traits

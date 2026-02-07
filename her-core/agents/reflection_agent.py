from pathlib import Path

from crewai import Agent

from agents.base_agent import BaseAgent


class ReflectionAgent(BaseAgent):
    def __init__(self, config_path: Path) -> None:
        super().__init__(config_path)
        self._config = self._config.get("reflection_agent", {})

    def build(self) -> Agent:
        return self.create_agent(
            role=self._config.get("role", "Memory Curator"),
            goal=self._config.get("goal", "Analyze conversations and store important memories"),
            temperature=self._config.get("temperature", 0.3),
        )

    def analyze_conversation(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        memories = []
        threshold = self._config.get("importance_threshold", 0.7)
        for message in messages:
            if message.get("role") == "user" and message.get("message"):
                importance = self.score_importance(message["message"])
                if importance < threshold:
                    continue
                memories.append(
                    {
                        "text": message["message"],
                        "category": "conversation",
                        "importance": importance,
                    }
                )
        return memories

    def score_importance(self, text: str) -> float:
        base = 0.5
        length_boost = min(len(text) / 200, 0.4)
        return round(min(1.0, base + length_boost), 2)

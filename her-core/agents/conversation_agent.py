from pathlib import Path
from typing import Any

from crewai import Agent

from agents.base_agent import BaseAgent


class ConversationAgent(BaseAgent):
    def __init__(self, config_path: Path) -> None:
        super().__init__(config_path)
        self._config = self._config.get("conversation_agent", {})

    def build(self, tools: list[Any] | None = None) -> Agent:
        return self.create_agent(
            role=self._config.get("role", "Empathetic Conversationalist"),
            goal=self._config.get("goal", "Engage users warmly while remembering context"),
            temperature=self._config.get("temperature", 0.7),
            max_tokens=self._config.get("max_tokens", 500),
            tools=tools or [],
        )

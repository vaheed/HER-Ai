from pathlib import Path
from typing import Any

from crewai import Agent

from agents.base_agent import BaseAgent


class ToolAgent(BaseAgent):
    def __init__(self, config_path: Path) -> None:
        super().__init__(config_path)
        self._config = self._config.get("tool_agent", {})

    def build(self, tools: list[Any] | None = None) -> Agent:
        return self.create_agent(
            role=self._config.get("role", "Task Executor"),
            goal=self._config.get("goal", "Safely execute external tools and operations"),
            backstory=self._config.get("backstory", "You execute external tools carefully, prioritize safety, and return concise actionable outputs to the crew."),
            temperature=self._config.get("temperature", 0.2),
            max_tokens=self._config.get("max_tokens", 400),
            tools=tools or [],
        )

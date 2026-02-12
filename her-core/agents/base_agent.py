import logging
from pathlib import Path
from typing import Any

import yaml
from crewai import Agent

from utils.config_paths import resolve_config_file
from utils.llm_factory import build_llm


class BaseAgent:
    def __init__(self, config_path: Path) -> None:
        self._config = self._load_config(config_path)
        self._logger = logging.getLogger(self.__class__.__name__)

    def create_agent(self, role: str, goal: str, **kwargs: Any) -> Agent:
        llm = build_llm()
        return Agent(
            role=role,
            goal=goal,
            llm=llm,
            **kwargs,
        )

    @staticmethod
    def _load_config(path: Path) -> dict[str, Any]:
        resolved_path = path
        if not resolved_path.exists():
            resolved_path = resolve_config_file(path.name)

        if not resolved_path.exists():
            raise FileNotFoundError(
                f"Config file '{path.name}' not found. Tried '{path}' and resolved fallback '{resolved_path}'."
            )

        with resolved_path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}

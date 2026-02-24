from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "her-ai"
    environment: str = "dev"
    log_level: str = "INFO"

    api_host: str = "127.0.0.1"
    api_port: int = 8000

    request_timeout_seconds: float = 20.0
    database_url: str = "postgresql+asyncpg://her:her@127.0.0.1:5432/her"
    redis_url: str = "redis://127.0.0.1:6379/0"
    working_memory_ttl_minutes: int = 30

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-sonnet-latest"

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.1:8b"

    provider_priority: List[str] = Field(default_factory=lambda: ["openai", "anthropic", "ollama"])

    @field_validator("provider_priority", mode="before")
    @classmethod
    def parse_provider_priority(cls, value: object) -> List[str]:
        """Support comma-separated or JSON-like provider priority values."""

        if isinstance(value, str):
            return [entry.strip() for entry in value.split(",") if entry.strip()]
        if isinstance(value, list):
            return [str(entry).strip() for entry in value if str(entry).strip()]
        return ["openai", "anthropic", "ollama"]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings to avoid repeated env parsing."""

    return Settings()

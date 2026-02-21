import os
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_csv(name: str) -> list[str]:
    value = os.getenv(name, "")
    return [item.strip() for item in value.split(",") if item.strip()]


def _valid_timezone_name(value: str, fallback: str = "UTC") -> str:
    candidate = (value or fallback).strip() or fallback
    try:
        ZoneInfo(candidate)
        return candidate
    except Exception:  # noqa: BLE001
        return fallback


@dataclass
class AppConfig:
    llm_provider: str = os.getenv("LLM_PROVIDER", "ollama")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    groq_api_key: str | None = os.getenv("GROQ_API_KEY")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    openrouter_api_key: str | None = os.getenv("OPENROUTER_API_KEY")
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")
    openrouter_api_base: str = os.getenv("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

    embedder_provider: str = os.getenv("EMBEDDER_PROVIDER", "ollama")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
    embedding_dimensions: int = int(os.getenv("EMBEDDING_DIMENSIONS", "768"))

    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")

    memory_vector_provider: str = os.getenv("MEMORY_VECTOR_PROVIDER", "pgvector")
    memory_collection_name: str = os.getenv("MEMORY_COLLECTION_NAME", "memories")
    memory_strict_mode: bool = _env_bool("MEMORY_STRICT_MODE", False)

    postgres_user: str = os.getenv("POSTGRES_USER", "her")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "changeme123")
    postgres_db: str = os.getenv("POSTGRES_DB", "her_memory")
    postgres_host: str = os.getenv("POSTGRES_HOST", "postgres")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))

    redis_host: str = os.getenv("REDIS_HOST", "redis")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_password: str = os.getenv("REDIS_PASSWORD", "changeme456")

    telegram_bot_token: str | None = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_admin_user_id: str | None = os.getenv("ADMIN_USER_ID")
    telegram_admin_user_ids: list[str] = field(default_factory=lambda: _env_csv("ADMIN_USER_ID"))
    telegram_public_approval_required: bool = _env_bool("TELEGRAM_PUBLIC_APPROVAL_REQUIRED", True)
    telegram_public_rate_limit_per_minute: int = int(os.getenv("TELEGRAM_PUBLIC_RATE_LIMIT_PER_MINUTE", "20"))
    telegram_enabled: bool = _env_bool("TELEGRAM_ENABLED", True)
    telegram_startup_retry_delay_seconds: int = int(os.getenv("TELEGRAM_STARTUP_RETRY_DELAY_SECONDS", "10"))
    autonomous_max_steps: int = int(os.getenv("HER_AUTONOMOUS_MAX_STEPS", "16"))
    sandbox_command_timeout_seconds: int = int(os.getenv("HER_SANDBOX_COMMAND_TIMEOUT_SECONDS", "60"))
    sandbox_cpu_time_limit_seconds: int = int(os.getenv("HER_SANDBOX_CPU_TIME_LIMIT_SECONDS", "20"))
    sandbox_memory_limit_mb: int = int(os.getenv("HER_SANDBOX_MEMORY_LIMIT_MB", "512"))
    startup_warmup_enabled: bool = _env_bool("STARTUP_WARMUP_ENABLED", False)
    workflow_debug_server_enabled: bool = _env_bool("WORKFLOW_DEBUG_SERVER_ENABLED", True)
    workflow_debug_host: str = os.getenv("WORKFLOW_DEBUG_HOST", "0.0.0.0")
    workflow_debug_port: int = int(os.getenv("WORKFLOW_DEBUG_PORT", "8081"))
    api_adapter_enabled: bool = _env_bool("API_ADAPTER_ENABLED", True)
    api_adapter_host: str = os.getenv("API_ADAPTER_HOST", "0.0.0.0")
    api_adapter_port: int = int(os.getenv("API_ADAPTER_PORT", "8082"))
    api_adapter_bearer_token: str = os.getenv("API_ADAPTER_BEARER_TOKEN", "")
    api_adapter_model_name: str = os.getenv("API_ADAPTER_MODEL_NAME", "her-chat-1")
    system_timezone: str = _valid_timezone_name(os.getenv("TZ", "UTC"), "UTC")
    default_user_timezone: str = _valid_timezone_name(os.getenv("USER_TIMEZONE", "UTC"), "UTC")

    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    environment: str = os.getenv("ENVIRONMENT", "development")

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class AppConfig:
    llm_provider: str = os.getenv("LLM_PROVIDER", "ollama")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    groq_api_key: str | None = os.getenv("GROQ_API_KEY")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

    embedder_provider: str = os.getenv("EMBEDDER_PROVIDER", "ollama")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
    embedding_dimensions: int = int(os.getenv("EMBEDDING_DIMENSIONS", "768"))

    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")

    memory_vector_provider: str = os.getenv("MEMORY_VECTOR_PROVIDER", "pgvector")
    memory_collection_name: str = os.getenv("MEMORY_COLLECTION_NAME", "memories")

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
    telegram_enabled: bool = _env_bool("TELEGRAM_ENABLED", True)
    telegram_startup_retry_delay_seconds: int = int(os.getenv("TELEGRAM_STARTUP_RETRY_DELAY_SECONDS", "10"))

    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    environment: str = os.getenv("ENVIRONMENT", "development")

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class AppConfig:
    llm_provider: str = os.getenv("LLM_PROVIDER", "openai")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    groq_api_key: str | None = os.getenv("GROQ_API_KEY")

    postgres_user: str = os.getenv("POSTGRES_USER", "her")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "changeme123")
    postgres_db: str = os.getenv("POSTGRES_DB", "her_memory")
    postgres_host: str = os.getenv("POSTGRES_HOST", "postgres")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))

    redis_host: str = os.getenv("REDIS_HOST", "redis")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_password: str = os.getenv("REDIS_PASSWORD", "changeme456")

    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    environment: str = os.getenv("ENVIRONMENT", "development")

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

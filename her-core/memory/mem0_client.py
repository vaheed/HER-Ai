import logging
from typing import Any

from mem0 import Memory

from config import AppConfig
from memory.redis_client import RedisContextStore
from utils.retry import RetryError, with_retry

logger = logging.getLogger("her-memory")


def _retry_root_cause_message(exc: RetryError) -> str:
    root = exc.__cause__ or exc
    return f"{root.__class__.__name__}: {root}"


def _is_ollama_low_memory_error(message: str) -> bool:
    lower = message.lower()
    return "model requires more system memory" in lower and "than is available" in lower


def _normalize_search_results(results: object) -> list[dict[str, Any]]:
    if isinstance(results, list):
        return [item for item in results if isinstance(item, dict)]
    if isinstance(results, dict):
        raw_items = results.get("results") or results.get("memories") or []
        if isinstance(raw_items, list):
            return [item for item in raw_items if isinstance(item, dict)]
    return []


class HERMemory:
    def __init__(self, config: AppConfig, context_store: RedisContextStore) -> None:
        self._context_store = context_store
        self._config = config

        llm_config = self._build_llm_config(config)
        embedder_config = self._build_embedder_config(config)

        self._mem0 = Memory.from_config(
            {
                "vector_store": {
                    "provider": config.memory_vector_provider,
                    "config": {
                        "collection_name": config.memory_collection_name,
                        "host": config.postgres_host,
                        "port": config.postgres_port,
                        "dbname": config.postgres_db,
                        "user": config.postgres_user,
                        "password": config.postgres_password,
                        "embedding_model_dims": config.embedding_dimensions,
                    },
                },
                "llm": {
                    "provider": config.llm_provider,
                    "config": llm_config,
                },
                "embedder": {
                    "provider": config.embedder_provider,
                    "config": embedder_config,
                },
                "collection_name": config.memory_collection_name,
                "embedding_model_dims": config.embedding_dimensions,
            }
        )

    @staticmethod
    def _build_llm_config(config: AppConfig) -> dict[str, Any]:
        if config.llm_provider == "openai":
            return {"api_key": config.openai_api_key, "model": config.openai_model}
        if config.llm_provider == "groq":
            return {"api_key": config.groq_api_key, "model": config.groq_model}
        if config.llm_provider == "openrouter":
            return {
                "api_key": config.openrouter_api_key,
                "model": config.openrouter_model,
                "openai_base_url": config.openrouter_api_base,
            }
        if config.llm_provider == "ollama":
            return {"model": config.ollama_model, "ollama_base_url": config.ollama_base_url}
        return {}

    @staticmethod
    def _build_embedder_config(config: AppConfig) -> dict[str, Any]:
        if config.embedder_provider == "openai":
            return {"api_key": config.openai_api_key, "model": config.embedding_model}
        if config.embedder_provider == "ollama":
            return {"model": config.embedding_model, "ollama_base_url": config.ollama_base_url}
        return {"model": config.embedding_model}

    def add_memory(self, user_id: str, text: str, category: str, importance: float) -> dict[str, Any]:
        try:
            return with_retry(
                lambda: self._mem0.add(
                    text,
                    user_id=user_id,
                    metadata={"category": category, "importance": importance},
                )
            )
        except RetryError as exc:
            if self._config.memory_strict_mode:
                raise
            cause_message = _retry_root_cause_message(exc)
            if _is_ollama_low_memory_error(cause_message):
                logger.warning(
                    "Memory add skipped for user %s due to Ollama RAM limits (%s). "
                    "Use a smaller OLLAMA_MODEL or increase container memory.",
                    user_id,
                    cause_message,
                )
            else:
                logger.warning(
                    "Memory add skipped for user %s after retries (%s); continuing without long-term memory.",
                    user_id,
                    cause_message,
                )
            return {"status": "skipped", "reason": "memory_backend_unavailable", "detail": cause_message}

    def search_memories(self, user_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        try:
            results = with_retry(lambda: self._mem0.search(query, user_id=user_id, limit=limit))
            return _normalize_search_results(results)
        except RetryError as exc:
            if self._config.memory_strict_mode:
                raise
            cause_message = _retry_root_cause_message(exc)
            if _is_ollama_low_memory_error(cause_message):
                logger.warning(
                    "Memory search skipped for user %s due to Ollama RAM limits (%s). "
                    "Falling back to short-term context only.",
                    user_id,
                    cause_message,
                )
            else:
                logger.warning(
                    "Memory search skipped for user %s after retries (%s); falling back to short-term context only.",
                    user_id,
                    cause_message,
                )
            return []

    def update_memory(self, memory_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        if not hasattr(self._mem0, "update"):
            raise NotImplementedError("Mem0 update operation is not available in this version.")
        return with_retry(lambda: self._mem0.update(memory_id, updates))

    def delete_memory(self, memory_id: str) -> dict[str, Any]:
        if not hasattr(self._mem0, "delete"):
            raise NotImplementedError("Mem0 delete operation is not available in this version.")
        return with_retry(lambda: self._mem0.delete(memory_id))

    def get_context(self, user_id: str) -> list[dict[str, Any]]:
        return self._context_store.get(self._context_key(user_id))

    def update_context(self, user_id: str, message: str, role: str, max_messages: int = 20) -> list[dict[str, Any]]:
        return self._context_store.append(
            self._context_key(user_id),
            {"role": role, "message": message},
            max_messages,
        )

    @staticmethod
    def _context_key(user_id: str) -> str:
        return f"her:context:{user_id}"

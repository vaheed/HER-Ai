from typing import Any

from mem0 import Memory

from config import AppConfig
from memory.redis_client import RedisContextStore
from utils.retry import with_retry


class HERMemory:
    def __init__(self, config: AppConfig, context_store: RedisContextStore) -> None:
        self._context_store = context_store
        self._mem0 = Memory.from_config(
            {
                "vector_store": {
                    "provider": "pgvector",
                    "config": {
                        "collection_name": "memories",
                        "host": config.postgres_host,
                        "port": config.postgres_port,
                        "db_name": config.postgres_db,
                        "user": config.postgres_user,
                        "password": config.postgres_password,
                    },
                },
                "llm": {
                    "provider": config.llm_provider,
                    "config": {
                        "api_key": config.openai_api_key if config.llm_provider == "openai" else config.groq_api_key,
                        "model": "text-embedding-3-small",
                    },
                },
            }
        )

    def add_memory(self, user_id: str, text: str, category: str, importance: float) -> dict[str, Any]:
        return with_retry(
            lambda: self._mem0.add(
                text,
                user_id=user_id,
                metadata={"category": category, "importance": importance},
            )
        )

    def search_memories(self, user_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        return with_retry(lambda: self._mem0.search(query, user_id=user_id, limit=limit))

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

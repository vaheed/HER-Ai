from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


class MemoryDatabase:
    """Async SQLAlchemy engine/session manager for memory operations."""

    def __init__(self, database_url: str, echo: bool = False) -> None:
        self._engine: AsyncEngine = create_async_engine(database_url, echo=echo, pool_pre_ping=True)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

    @property
    def engine(self) -> AsyncEngine:
        """Return the underlying async engine."""

        return self._engine

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield an async session."""

        async with self._session_factory() as session:
            yield session

    async def healthcheck(self) -> bool:
        """Return whether database is reachable."""

        try:
            async with self.session() as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    async def dispose(self) -> None:
        """Dispose database engine and pooled connections."""

        await self._engine.dispose()

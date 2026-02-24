from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import Select, func, select

from her.models import Episode
from her.memory.db import MemoryDatabase
from her.memory.models import (
    EpisodeORM,
    GoalORM,
    LLMUsageLogORM,
    PersonalitySnapshotORM,
    SemanticMemoryORM,
)
from her.memory.types import GoalRecord, PersonalitySnapshotRecord, SemanticMemoryRecord


class MemoryStore:
    """Async CRUD and lifecycle operations for memory-related tables."""

    def __init__(self, database: MemoryDatabase) -> None:
        self._database = database

    async def add_episode(
        self,
        session_id: UUID,
        content: str,
        importance_score: float = 0.5,
        emotional_valence: float = 0.0,
        embedding: Optional[List[float]] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Episode:
        """Insert an episode and return the canonical model."""

        payload_metadata = metadata or {}
        episode_row = EpisodeORM(
            session_id=session_id,
            content=content,
            embedding=embedding,
            emotional_valence=max(-1.0, min(1.0, emotional_valence)),
            importance_score=max(0.0, min(1.0, importance_score)),
            decay_factor=1.0,
            archived=False,
            metadata_json=payload_metadata,
        )

        async with self._database.session() as session:
            session.add(episode_row)
            await session.flush()
            await session.commit()
            await session.refresh(episode_row)

        return _episode_from_orm(episode_row)

    async def list_session_episodes(self, session_id: UUID, include_archived: bool = False) -> List[Episode]:
        """List episodes for a session ordered by timestamp."""

        stmt: Select[tuple[EpisodeORM]] = (
            select(EpisodeORM)
            .where(EpisodeORM.session_id == session_id)
            .order_by(EpisodeORM.timestamp.asc())
        )
        if not include_archived:
            stmt = stmt.where(EpisodeORM.archived.is_(False))

        async with self._database.session() as session:
            rows = (await session.execute(stmt)).scalars().all()

        return [_episode_from_orm(row) for row in rows]

    async def upsert_semantic_concept(
        self,
        concept: str,
        summary: str,
        episode_id: UUID,
        tags: Optional[List[str]] = None,
        embedding: Optional[List[float]] = None,
    ) -> SemanticMemoryRecord:
        """Create or reinforce a semantic concept record."""

        normalized = concept.strip()
        input_tags = tags or []

        async with self._database.session() as session:
            stmt: Select[tuple[SemanticMemoryORM]] = select(SemanticMemoryORM).where(
                func.lower(SemanticMemoryORM.concept) == normalized.lower()
            )
            existing = (await session.execute(stmt)).scalars().first()

            if existing is None:
                record = SemanticMemoryORM(
                    concept=normalized,
                    summary=summary,
                    embedding=embedding,
                    confidence=1.0,
                    source_episode_ids=[episode_id],
                    last_reinforced=datetime.utcnow(),
                    tags=input_tags,
                )
                session.add(record)
                await session.flush()
                await session.commit()
                await session.refresh(record)
                return _semantic_from_orm(record)

            existing.summary = summary
            existing.embedding = embedding or existing.embedding
            existing.confidence = min(1.0, existing.confidence + 0.05)
            existing.last_reinforced = datetime.utcnow()
            if episode_id not in existing.source_episode_ids:
                existing.source_episode_ids.append(episode_id)
            for tag in input_tags:
                if tag not in existing.tags:
                    existing.tags.append(tag)

            await session.commit()
            await session.refresh(existing)
            return _semantic_from_orm(existing)

    async def semantic_search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        min_confidence: float = 0.0,
    ) -> List[SemanticMemoryRecord]:
        """Return nearest semantic records by cosine distance."""

        stmt: Select[tuple[SemanticMemoryORM]] = (
            select(SemanticMemoryORM)
            .where(SemanticMemoryORM.embedding.is_not(None))
            .where(SemanticMemoryORM.confidence >= min_confidence)
            .order_by(SemanticMemoryORM.embedding.cosine_distance(query_embedding))
            .limit(max(1, top_k))
        )

        async with self._database.session() as session:
            rows = (await session.execute(stmt)).scalars().all()

        return [_semantic_from_orm(row) for row in rows]

    async def list_semantic_records(self) -> List[SemanticMemoryRecord]:
        """Return all semantic records."""

        stmt: Select[tuple[SemanticMemoryORM]] = select(SemanticMemoryORM).order_by(
            SemanticMemoryORM.created_at.asc()
        )
        async with self._database.session() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [_semantic_from_orm(row) for row in rows]

    async def create_goal(self, description: str, priority: float = 0.5) -> GoalRecord:
        """Insert a goal row and return a transfer object."""

        goal_row = GoalORM(
            description=description,
            status="active",
            priority=max(0.0, min(1.0, priority)),
            metadata_json={},
            linked_episodes=[],
        )
        async with self._database.session() as session:
            session.add(goal_row)
            await session.flush()
            await session.commit()
            await session.refresh(goal_row)
        return _goal_from_orm(goal_row)

    async def decay_and_archive_episodes(self, daily_decay: float = 0.95) -> int:
        """Decay episode relevance and archive stale low-importance rows."""

        archived_count = 0
        stmt: Select[tuple[EpisodeORM]] = select(EpisodeORM).where(EpisodeORM.archived.is_(False))

        async with self._database.session() as session:
            rows = (await session.execute(stmt)).scalars().all()
            for row in rows:
                row.decay_factor = round(row.decay_factor * daily_decay, 4)
                if row.decay_factor < 0.1 and row.importance_score < 0.3:
                    row.archived = True
                    archived_count += 1
            await session.commit()

        return archived_count

    async def decay_semantic_confidence(self, weekly_decay: float = 0.05) -> int:
        """Decay semantic confidence for all records."""

        updated = 0
        stmt: Select[tuple[SemanticMemoryORM]] = select(SemanticMemoryORM)
        async with self._database.session() as session:
            rows = (await session.execute(stmt)).scalars().all()
            for row in rows:
                row.confidence = max(0.0, round(row.confidence - weekly_decay, 3))
                updated += 1
            await session.commit()
        return updated

    async def flag_dormant_goals(self, days_without_progress: int = 14) -> int:
        """Mark goals as dormant when stale."""

        cutoff = datetime.utcnow() - timedelta(days=days_without_progress)
        updated = 0

        stmt: Select[tuple[GoalORM]] = select(GoalORM).where(GoalORM.status == "active")
        async with self._database.session() as session:
            rows = (await session.execute(stmt)).scalars().all()
            for row in rows:
                stale = row.last_progressed is None or row.last_progressed < cutoff
                if stale:
                    row.status = "dormant"
                    updated += 1
            await session.commit()

        return updated

    async def record_llm_usage(
        self,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        latency_ms: int,
        episode_id: Optional[UUID],
    ) -> None:
        """Persist LLM cost and latency metadata."""

        row = LLMUsageLogORM(
            provider=provider,
            model=model,
            prompt_tokens=max(0, prompt_tokens),
            completion_tokens=max(0, completion_tokens),
            cost_usd=max(0.0, cost_usd),
            latency_ms=max(0, latency_ms),
            episode_id=episode_id,
        )
        async with self._database.session() as session:
            session.add(row)
            await session.commit()

    async def create_personality_snapshot(
        self,
        traits: Dict[str, float],
        emotional_baseline: Dict[str, float | str | None],
        drift_delta: Optional[Dict[str, float]] = None,
        trigger_summary: Optional[str] = None,
    ) -> None:
        """Persist a personality snapshot row."""

        emotional_payload: Dict[str, Any] = dict(emotional_baseline)
        row = PersonalitySnapshotORM(
            traits=traits,
            emotional_baseline=emotional_payload,
            drift_delta=drift_delta,
            trigger_summary=trigger_summary,
        )
        async with self._database.session() as session:
            session.add(row)
            await session.commit()

    async def get_latest_personality_snapshot(self) -> Optional[PersonalitySnapshotRecord]:
        """Return the latest persisted personality snapshot if available."""

        stmt: Select[tuple[PersonalitySnapshotORM]] = (
            select(PersonalitySnapshotORM).order_by(PersonalitySnapshotORM.snapshot_at.desc()).limit(1)
        )
        async with self._database.session() as session:
            row = (await session.execute(stmt)).scalars().first()
        if row is None:
            return None

        emotional_payload: Dict[str, float | str | None] = {
            str(key): value for key, value in row.emotional_baseline.items()
        }
        drift_delta: Optional[Dict[str, float]] = None
        if row.drift_delta is not None:
            drift_delta = {str(key): float(value) for key, value in row.drift_delta.items()}

        return PersonalitySnapshotRecord(
            snapshot_at=row.snapshot_at,
            traits={str(key): float(value) for key, value in row.traits.items()},
            emotional_baseline=emotional_payload,
            drift_delta=drift_delta,
            trigger_summary=row.trigger_summary,
        )



def _episode_from_orm(row: EpisodeORM) -> Episode:
    timestamp = row.timestamp
    metadata_dict = {str(k): str(v) for k, v in row.metadata_json.items()}
    return Episode(
        id=row.id,
        session_id=row.session_id,
        timestamp=timestamp,
        content=row.content,
        embedding=list(row.embedding) if row.embedding is not None else None,
        emotional_valence=float(row.emotional_valence),
        importance_score=float(row.importance_score),
        decay_factor=float(row.decay_factor),
        archived=bool(row.archived),
        metadata=metadata_dict,
    )



def _semantic_from_orm(row: SemanticMemoryORM) -> SemanticMemoryRecord:
    reinforced = row.last_reinforced or row.created_at
    return SemanticMemoryRecord(
        id=row.id,
        concept=row.concept,
        summary=row.summary,
        confidence=float(row.confidence),
        source_episode_ids=list(row.source_episode_ids),
        last_reinforced=reinforced,
        created_at=row.created_at,
        tags=list(row.tags),
    )



def _goal_from_orm(row: GoalORM) -> GoalRecord:
    return GoalRecord(
        id=row.id,
        description=row.description,
        status=row.status,
        priority=float(row.priority),
        created_at=row.created_at,
        last_progressed=row.last_progressed,
        linked_episodes=list(row.linked_episodes),
        metadata={str(k): str(v) for k, v in row.metadata_json.items()},
    )

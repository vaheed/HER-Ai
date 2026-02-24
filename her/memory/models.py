from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """Declarative metadata root for memory schema."""


class EpisodeORM(Base):
    """Episodic memory row."""

    __tablename__ = "episodes"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    session_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Optional[List[float]]] = mapped_column(Vector(1536), nullable=True)
    emotional_valence: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0.0"))
    importance_score: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0.5"))
    decay_factor: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("1.0"))
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class SemanticMemoryORM(Base):
    """Semantic memory row."""

    __tablename__ = "semantic_memory"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    concept: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    embedding: Mapped[Optional[List[float]]] = mapped_column(Vector(1536), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("1.0"))
    source_episode_ids: Mapped[List[UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)), nullable=False, server_default=text("'{}'::uuid[]")
    )
    last_reinforced: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    tags: Mapped[List[str]] = mapped_column(ARRAY(String()), nullable=False, server_default=text("'{}'::text[]"))


class GoalORM(Base):
    """Goal registry row."""

    __tablename__ = "goals"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'active'"))
    priority: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0.5"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_progressed: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    linked_episodes: Mapped[List[UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)), nullable=False, server_default=text("'{}'::uuid[]")
    )
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class PersonalitySnapshotORM(Base):
    """Versioned personality snapshot row."""

    __tablename__ = "personality_snapshots"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    traits: Mapped[Dict[str, float]] = mapped_column(JSONB, nullable=False)
    emotional_baseline: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    drift_delta: Mapped[Optional[Dict[str, float]]] = mapped_column(JSONB, nullable=True)
    trigger_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class RelationshipStateORM(Base):
    """Relationship and trust state row."""

    __tablename__ = "relationship_state"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    trust_score: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0.5"))
    engagement_score: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0.5"))
    interaction_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    detected_biases: Mapped[List[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))


class LLMUsageLogORM(Base):
    """LLM usage accounting row."""

    __tablename__ = "llm_usage_log"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    episode_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("episodes.id", ondelete="SET NULL"), nullable=True
    )

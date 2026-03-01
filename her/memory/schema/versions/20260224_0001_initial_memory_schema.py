"""Initial memory schema with pgvector support.

Revision ID: 20260224_0001
Revises:
Create Date: 2026-02-24 00:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260224_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "episodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("emotional_valence", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("importance_score", sa.Float(), nullable=False, server_default=sa.text("0.5")),
        sa.Column("decay_factor", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_episodes_session_id", "episodes", ["session_id"], unique=False)

    op.create_table(
        "semantic_memory",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("concept", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("source_episode_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False, server_default=sa.text("'{}'::uuid[]")),
        sa.Column("last_reinforced", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_semantic_memory_concept", "semantic_memory", ["concept"], unique=False)

    op.create_table(
        "goals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'active'")),
        sa.Column("priority", sa.Float(), nullable=False, server_default=sa.text("0.5")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_progressed", sa.DateTime(timezone=True), nullable=True),
        sa.Column("linked_episodes", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False, server_default=sa.text("'{}'::uuid[]")),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "personality_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("traits", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("emotional_baseline", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("drift_delta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("trigger_summary", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "relationship_state",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("trust_score", sa.Float(), nullable=False, server_default=sa.text("0.5")),
        sa.Column("engagement_score", sa.Float(), nullable=False, server_default=sa.text("0.5")),
        sa.Column("interaction_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("detected_biases", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "llm_usage_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("episode_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("llm_usage_log")
    op.drop_table("relationship_state")
    op.drop_table("personality_snapshots")
    op.drop_table("goals")
    op.drop_index("ix_semantic_memory_concept", table_name="semantic_memory")
    op.drop_table("semantic_memory")
    op.drop_index("ix_episodes_session_id", table_name="episodes")
    op.drop_table("episodes")

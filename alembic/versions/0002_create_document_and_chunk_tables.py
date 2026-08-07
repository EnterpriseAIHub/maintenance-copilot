"""create document and chunk tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-08

Adds the two tables Phase 2 needs. No document_version, audit_log, or
Redis-related tables — those are deliberately deferred (see EDD §20 /
PROJECT_PROGRESS.md). `document.status` includes 'archived' (not in the
EDD's original enum literal) to support the soft-delete DELETE endpoint
the EDD's API design section already specified — see PROJECT_PROGRESS.md
for this Phase 2 architectural note.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None

EMBEDDING_DIMENSION = 1536


def upgrade() -> None:
    op.create_table(
        "document",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("equipment_id", sa.String(), nullable=True),
        sa.Column("plant_id", sa.String(), nullable=True),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("uploaded_by", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('processing', 'active', 'failed', 'archived')",
            name="ck_document_status",
        ),
        sa.CheckConstraint(
            "source_type IN ('manual', 'sop', 'work_order_export', 'other')",
            name="ck_document_source_type",
        ),
    )
    op.create_index("ix_document_equipment_status", "document", ["equipment_id", "status"])

    op.create_table(
        "chunk",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSION), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_chunk_document_id", "chunk", ["document_id"])
    op.execute(
        "CREATE INDEX ix_chunk_embedding ON chunk "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    op.drop_index("ix_chunk_embedding", table_name="chunk")
    op.drop_index("ix_chunk_document_id", table_name="chunk")
    op.drop_table("chunk")
    op.drop_index("ix_document_equipment_status", table_name="document")
    op.drop_table("document")

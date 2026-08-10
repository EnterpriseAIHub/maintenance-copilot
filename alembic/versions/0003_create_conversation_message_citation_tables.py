"""create conversation, message, and citation tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-07

Phase 4 tables. `citation.chunk_id`/`citation.document_id` use ON DELETE
SET NULL, not CASCADE — a citation's own denormalized section_title/
page_number/snippet columns are enough to stay meaningful even after the
source chunk (e.g. a later reindex) or document is removed. See
PROJECT_PROGRESS.md for the Phase 4 architectural note this mirrors from
Phase 2's document.error_message.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.create_table(
        "conversation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("equipment_id", sa.String(), nullable=True),
        sa.Column("plant_id", sa.String(), nullable=True),
        sa.Column("started_by", sa.String(), nullable=False),
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
    )

    op.create_table(
        "message",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversation.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("retrieved_chunk_count", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_message_role"),
    )
    op.create_index("ix_message_conversation_id", "message", ["conversation_id"])

    op.create_table(
        "citation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("message.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chunk_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chunk.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("section_title", sa.String(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_citation_message_id", "citation", ["message_id"])


def downgrade() -> None:
    op.drop_index("ix_citation_message_id", table_name="citation")
    op.drop_table("citation")
    op.drop_index("ix_message_conversation_id", table_name="message")
    op.drop_table("message")
    op.drop_table("conversation")

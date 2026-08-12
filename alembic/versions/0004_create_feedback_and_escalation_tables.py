"""create feedback and escalation tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-08

Phase 5 tables. `escalation.conversation_id`/`confidence`/`answer_snapshot`
are denormalized copies taken at creation time — see
app/data/models/escalation.py's docstring for why (same reasoning as
Phase 4's citation table).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.create_table(
        "feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("message.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("helpful", sa.Boolean(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("submitted_by", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_feedback_message_id", "feedback", ["message_id"])

    op.create_table(
        "escalation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("message.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversation.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="open"),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("answer_snapshot", sa.Text(), nullable=False),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "reason IN ('low_confidence', 'negative_feedback')", name="ck_escalation_reason"
        ),
        sa.CheckConstraint("status IN ('open', 'resolved')", name="ck_escalation_status"),
    )
    op.create_index("ix_escalation_message_id", "escalation", ["message_id"])
    op.create_index("ix_escalation_status", "escalation", ["status"])


def downgrade() -> None:
    op.drop_index("ix_escalation_status", table_name="escalation")
    op.drop_index("ix_escalation_message_id", table_name="escalation")
    op.drop_table("escalation")
    op.drop_index("ix_feedback_message_id", table_name="feedback")
    op.drop_table("feedback")

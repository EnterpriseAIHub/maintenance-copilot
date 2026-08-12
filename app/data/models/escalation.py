"""Escalation model.

Represents one assistant message flagged for human review — either
automatically, because its confidence fell below
COPILOT_CONFIDENCE_THRESHOLD, or because a technician left `helpful=False`
feedback on it. See app/services/escalation_service.py for the one place
both triggers funnel through (specifically so the same message can't end
up with two open escalations from the two different trigger paths).

Deliberately does NOT have `assigned_to` or an `in_review` state —
routing/assignment across a team of reviewers is listed under
PROJECT_PROGRESS.md's platform-wide deferred table ("one reviewer, one
queue" is the stated scope for this phase). `status` is just
`open`/`resolved`; anyone can resolve anything.

`conversation_id`, `confidence`, and `answer_snapshot` are denormalized
copies taken at escalation-creation time, not derived via a join through
`message_id` — same reasoning as Phase 4's Citation model: a reviewer
scanning the queue (GET /escalations) needs to see what was actually said
and how confident the system was without an extra lookup per row, and
that shouldn't depend on the source message still being reachable any
particular way.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.data.base import Base

ESCALATION_REASONS = ("low_confidence", "negative_feedback")
ESCALATION_STATUSES = ("open", "resolved")


class Escalation(Base):
    __tablename__ = "escalation"
    __table_args__ = (
        CheckConstraint(f"reason IN {ESCALATION_REASONS}", name="ck_escalation_reason"),
        CheckConstraint(f"status IN {ESCALATION_STATUSES}", name="ck_escalation_status"),
        Index("ix_escalation_message_id", "message_id"),
        Index("ix_escalation_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    message_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("message.id", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("conversation.id", ondelete="CASCADE"),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    answer_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

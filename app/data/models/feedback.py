"""Feedback model.

One row per human feedback signal on an assistant message. `helpful` is a
plain boolean (thumbs up/down) rather than a Likert scale — the simplest
shape that still supports what this phase actually needs it to do:
`helpful=False` is one of the two triggers for creating an Escalation
(see app/services/escalation_service.py), alongside the system's own
low-confidence auto-trigger. A finer-grained scale would add UI/API
surface without changing what happens downstream.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.data.base import Base


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (Index("ix_feedback_message_id", "message_id"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    message_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("message.id", ondelete="CASCADE"),
        nullable=False,
    )
    helpful: Mapped[bool] = mapped_column(Boolean, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_by: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

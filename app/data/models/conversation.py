"""Conversation model.

A conversation is just a container for messages, scoped the same way a
document is (optional equipment_id/plant_id) so history can later be
filtered per-equipment the same way document listing already is. No
`status`/`title` — nothing in this phase's scope reads either, and adding
them now would be scaffolding ahead of need (same rule applied throughout
this repo, see PROJECT_PROGRESS.md).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.data.base import Base


class Conversation(Base):
    __tablename__ = "conversation"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    equipment_id: Mapped[str | None] = mapped_column(String, nullable=True)
    plant_id: Mapped[str | None] = mapped_column(String, nullable=True)
    started_by: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

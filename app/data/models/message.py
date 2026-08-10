"""Message model.

One row per turn in a conversation. `role='user'` rows are the question as
typed; `role='assistant'` rows are the generated answer. `confidence` and
`retrieved_chunk_count` only ever get set on assistant rows (mirroring
app/rag/orchestrator.py::RagAnswer) — left nullable rather than split into
a separate table, since a message is still fundamentally one thing
(one turn), not two entities.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.data.base import Base

MESSAGE_ROLES = ("user", "assistant")


class Message(Base):
    __tablename__ = "message"
    __table_args__ = (
        CheckConstraint(f"role IN {MESSAGE_ROLES}", name="ck_message_role"),
        Index("ix_message_conversation_id", "conversation_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("conversation.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    retrieved_chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

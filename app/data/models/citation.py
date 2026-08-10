"""Citation model.

Persists one row per Citation an assistant message's answer relied on
(see app/rag/citation_extractor.py::Citation for the in-memory shape this
mirrors). `section_title`, `page_number`, and `snippet` are copied at
write time rather than only derived via a join through `chunk_id` — a
citation should stay readable even after the source document is later
reindexed and its old chunks deleted (see chunk_id's ON DELETE SET NULL
below). This is the same reasoning as `document.error_message` in Phase
2: small, denormalized, and directly supports being able to show a
technician *what* was cited without depending on data that may no longer
exist.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.data.base import Base


class Citation(Base):
    __tablename__ = "citation"
    __table_args__ = (Index("ix_citation_message_id", "message_id"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    message_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("message.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Soft-ish references: SET NULL (not CASCADE) on delete, since a
    # citation's own denormalized fields below are enough to stay
    # meaningful even if the specific chunk (or, less likely, the
    # document itself) it pointed at is later removed.
    chunk_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("chunk.id", ondelete="SET NULL"), nullable=True
    )
    document_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("document.id", ondelete="SET NULL"), nullable=True
    )
    section_title: Mapped[str | None] = mapped_column(String, nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    snippet: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

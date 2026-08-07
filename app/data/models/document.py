"""Document model.

Owned by this repo (see EDD §11/NFR6). Deliberately has no version-history
table and no `superseded` lifecycle — a re-upload replaces this document's
chunks in place (see EDD §20 for why full version history is deferred).

`error_message` is a small addition beyond the EDD's original column list:
a single nullable text field capturing why ingestion failed, so a failed
document is diagnosable from the API/DB directly without needing the
dedicated audit_log table that's also deferred (§20). Logged in
PROJECT_PROGRESS.md as a Phase 2 architectural decision.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.data.base import Base

DOCUMENT_STATUSES = ("processing", "active", "failed", "archived")
SOURCE_TYPES = ("manual", "sop", "work_order_export", "other")


class Document(Base):
    __tablename__ = "document"
    __table_args__ = (
        CheckConstraint(f"status IN {DOCUMENT_STATUSES}", name="ck_document_status"),
        CheckConstraint(f"source_type IN {SOURCE_TYPES}", name="ck_document_source_type"),
        Index("ix_document_equipment_status", "equipment_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String, nullable=False)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    equipment_id: Mapped[str | None] = mapped_column(String, nullable=True)
    plant_id: Mapped[str | None] = mapped_column(String, nullable=True)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="processing")
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    uploaded_by: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

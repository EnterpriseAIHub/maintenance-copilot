"""Feedback schemas (Phase 5)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class FeedbackCreateRequest(BaseModel):
    helpful: bool
    comment: str | None = None


class FeedbackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    message_id: UUID
    helpful: bool
    comment: str | None
    submitted_by: str
    created_at: datetime


__all__ = ["FeedbackCreateRequest", "FeedbackRead"]

"""Escalation schemas (Phase 5)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EscalationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    message_id: UUID
    conversation_id: UUID
    reason: str
    status: str
    confidence: float
    answer_snapshot: str
    resolution_note: str | None
    created_at: datetime
    resolved_at: datetime | None


class EscalationResolveRequest(BaseModel):
    resolution_note: str | None = None


__all__ = ["EscalationRead", "EscalationResolveRequest"]

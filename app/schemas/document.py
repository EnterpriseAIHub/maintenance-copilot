"""Document request/response schemas.

First schema module in the repo — created now because Phase 2 is the
first phase whose endpoints need one, not created ahead of need in
Phase 1.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.data.models.document import DOCUMENT_STATUSES, SOURCE_TYPES


class DocumentCreateResponse(BaseModel):
    document_id: UUID
    status: str


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    source_type: str
    equipment_id: str | None
    plant_id: str | None
    status: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime


__all__ = ["DocumentCreateResponse", "DocumentRead", "DOCUMENT_STATUSES", "SOURCE_TYPES"]

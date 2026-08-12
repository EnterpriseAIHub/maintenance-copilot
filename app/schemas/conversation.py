"""Conversation, message, and citation schemas (Phase 4).

`CitationRead` here is deliberately its own type, not a reuse of
app/schemas/query.py::CitationRead, even though the fields line up:
a *persisted* citation's `chunk_id`/`document_id` are nullable (the
underlying chunk or document row can later be removed — see
app/data/models/citation.py's ON DELETE SET NULL), whereas the
in-flight orchestrator.Citation these come from always has both set.
Reusing the non-nullable Phase 3 type here would either be wrong (lie
about nullability) or force loosening a type Phase 3 already got right
for its own use case.

`MessageRead.escalated` (Phase 5) reflects whether an *open* Escalation
currently exists for that message — see app/services/escalation_service.py.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ConversationCreateRequest(BaseModel):
    equipment_id: str | None = None
    plant_id: str | None = None


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    equipment_id: str | None
    plant_id: str | None
    started_by: str
    created_at: datetime
    updated_at: datetime


class MessageCreateRequest(BaseModel):
    question: str


class CitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chunk_id: UUID | None
    document_id: UUID | None
    section_title: str | None
    page_number: int | None
    snippet: str


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    role: str
    content: str
    confidence: float | None
    retrieved_chunk_count: int | None
    citations: list[CitationRead]
    escalated: bool
    created_at: datetime


__all__ = [
    "ConversationCreateRequest",
    "ConversationRead",
    "MessageCreateRequest",
    "CitationRead",
    "MessageRead",
]

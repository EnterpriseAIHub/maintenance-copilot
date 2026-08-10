"""Stateless query request/response schemas (Phase 3 debug endpoint).

No conversation/message persistence yet — see PROJECT_PROGRESS.md §9. This
response shape is expected to become the "answer" portion of Phase 4's
conversation message response, not a throwaway.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class QueryRequest(BaseModel):
    question: str
    equipment_id: str | None = None
    plant_id: str | None = None


class CitationRead(BaseModel):
    chunk_id: UUID
    document_id: UUID
    section_title: str | None
    page_number: int | None
    snippet: str


class QueryResponse(BaseModel):
    answer: str
    citations: list[CitationRead]
    confidence: float
    retrieved_chunk_count: int


__all__ = ["QueryRequest", "CitationRead", "QueryResponse"]

"""Stateless RAG query endpoint (Phase 3 debug/eval surface).

No persistence — this exists to exercise and evaluate the retrieval ->
LLM -> citation -> confidence pipeline (app/rag/orchestrator.py) ahead of
Phase 4 wiring the same orchestrator into a persisted /conversations flow.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.rag.orchestrator import answer_question
from app.schemas.query import CitationRead, QueryRequest, QueryResponse
from app.services.errors import ValidationError

router = APIRouter(tags=["query"])


@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest, db: Session = Depends(get_db)) -> QueryResponse:
    if not request.question.strip():
        raise ValidationError("question must not be empty", detail={"question": request.question})

    result = answer_question(
        db,
        request.question,
        equipment_id=request.equipment_id,
        plant_id=request.plant_id,
    )
    return QueryResponse(
        answer=result.answer,
        citations=[
            CitationRead(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                section_title=c.section_title,
                page_number=c.page_number,
                snippet=c.snippet,
            )
            for c in result.citations
        ],
        confidence=result.confidence,
        retrieved_chunk_count=result.retrieved_chunk_count,
    )

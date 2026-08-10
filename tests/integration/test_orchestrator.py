"""Integration tests for app/rag/orchestrator.py against a real
Postgres+pgvector instance, using the fake embedding and LLM clients
(deterministic, no network) — see their docstrings for why that's enough
to exercise the full retrieval -> prompt -> citation -> confidence
pipeline without needing real provider keys.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.data.models.chunk import Chunk
from app.data.models.document import Document
from app.rag.embedding_client import FakeEmbeddingClient
from app.rag.llm_client import FakeLLMClient
from app.rag.orchestrator import answer_question

pytestmark = pytest.mark.integration

_embedding_client = FakeEmbeddingClient()
_llm_client = FakeLLMClient()


def _seed_document_with_chunk(db: Session, *, equipment_id: str = "EQ-1", text: str) -> Chunk:
    document = Document(
        id=uuid4(),
        title="Test Doc",
        source_type="manual",
        equipment_id=equipment_id,
        plant_id=None,
        file_path="unused",
        status="active",
        uploaded_by="tester",
    )
    db.add(document)
    db.flush()

    [embedding] = _embedding_client.embed([text])
    chunk = Chunk(
        id=uuid4(),
        document_id=document.id,
        chunk_index=0,
        text=text,
        token_count=10,
        embedding=embedding,
        chunk_metadata={"section_title": "LUBRICATION", "page_number": 1},
    )
    db.add(chunk)
    db.commit()
    return chunk


def test_answer_question_returns_grounded_citation(db_session: Session) -> None:
    chunk = _seed_document_with_chunk(db_session, text="Lubricate bearing every 2000 hours.")

    result = answer_question(
        db_session,
        "How often should the bearing be lubricated?",
        embedding_client=_embedding_client,
        llm_client=_llm_client,
    )

    assert result.retrieved_chunk_count == 1
    assert len(result.citations) == 1
    assert result.citations[0].chunk_id == chunk.id
    assert result.citations[0].section_title == "LUBRICATION"
    assert result.confidence > 0.0


def test_answer_question_filters_by_equipment_id(db_session: Session) -> None:
    _seed_document_with_chunk(db_session, equipment_id="EQ-A", text="Content for equipment A.")
    _seed_document_with_chunk(db_session, equipment_id="EQ-B", text="Content for equipment B.")

    result = answer_question(
        db_session,
        "Tell me about this equipment.",
        equipment_id="EQ-A",
        embedding_client=_embedding_client,
        llm_client=_llm_client,
    )

    assert result.retrieved_chunk_count == 1


def test_answer_question_with_no_ingested_documents_returns_zero_confidence(
    db_session: Session,
) -> None:
    result = answer_question(
        db_session,
        "Anything about a pump that doesn't exist?",
        embedding_client=_embedding_client,
        llm_client=_llm_client,
    )

    assert result.retrieved_chunk_count == 0
    assert result.citations == []
    assert result.confidence == 0.0

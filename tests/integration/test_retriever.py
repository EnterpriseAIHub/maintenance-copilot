"""Integration tests for app/rag/retriever.py against a real
Postgres+pgvector instance, using the fake (deterministic) embedding
client so retrieval-quality assertions can be exact rather than fuzzy —
see FakeEmbeddingClient's docstring.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.data.models.chunk import Chunk
from app.data.models.document import Document
from app.rag.embedding_client import FakeEmbeddingClient
from app.rag.retriever import retrieve

pytestmark = pytest.mark.integration

_embedding_client = FakeEmbeddingClient()


def _make_document(
    db: Session,
    *,
    equipment_id: str | None = None,
    plant_id: str | None = None,
    status: str = "active",
) -> Document:
    document = Document(
        id=uuid4(),
        title="Test Doc",
        source_type="manual",
        equipment_id=equipment_id,
        plant_id=plant_id,
        file_path="unused",
        status=status,
        uploaded_by="tester",
    )
    db.add(document)
    db.flush()
    return document


def _make_chunk(db: Session, document: Document, text: str) -> Chunk:
    [embedding] = _embedding_client.embed([text])
    chunk = Chunk(
        id=uuid4(),
        document_id=document.id,
        chunk_index=0,
        text=text,
        token_count=10,
        embedding=embedding,
        chunk_metadata={"section_title": None, "page_number": None},
    )
    db.add(chunk)
    db.flush()
    return chunk


def test_retrieve_returns_exact_match_first(db_session: Session) -> None:
    document = _make_document(db_session)
    target = _make_chunk(db_session, document, "Bearing lubrication interval is 2000 hours.")
    _make_chunk(db_session, document, "Unrelated content about belt tension.")
    db_session.commit()

    [query_embedding] = _embedding_client.embed(["Bearing lubrication interval is 2000 hours."])

    results = retrieve(db_session, query_embedding, top_k=5)

    assert results[0].chunk.id == target.id
    assert results[0].similarity == pytest.approx(1.0, abs=1e-6)


def test_retrieve_filters_by_equipment_id(db_session: Session) -> None:
    doc_a = _make_document(db_session, equipment_id="EQ-A")
    doc_b = _make_document(db_session, equipment_id="EQ-B")
    _make_chunk(db_session, doc_a, "Content for equipment A.")
    chunk_b = _make_chunk(db_session, doc_b, "Content for equipment B.")
    db_session.commit()

    [query_embedding] = _embedding_client.embed(["Content for equipment B."])

    results = retrieve(db_session, query_embedding, equipment_id="EQ-B", top_k=5)

    assert len(results) == 1
    assert results[0].chunk.id == chunk_b.id


def test_retrieve_filters_by_plant_id(db_session: Session) -> None:
    doc_a = _make_document(db_session, plant_id="PLANT-1")
    doc_b = _make_document(db_session, plant_id="PLANT-2")
    chunk_a = _make_chunk(db_session, doc_a, "Content at plant one.")
    _make_chunk(db_session, doc_b, "Content at plant two.")
    db_session.commit()

    [query_embedding] = _embedding_client.embed(["Content at plant one."])

    results = retrieve(db_session, query_embedding, plant_id="PLANT-1", top_k=5)

    assert len(results) == 1
    assert results[0].chunk.id == chunk_a.id


def test_retrieve_excludes_non_active_documents(db_session: Session) -> None:
    document = _make_document(db_session, status="processing")
    chunk = _make_chunk(db_session, document, "Content that should not surface.")
    db_session.commit()

    [query_embedding] = _embedding_client.embed(["Content that should not surface."])

    results = retrieve(db_session, query_embedding, top_k=5)

    assert chunk.id not in {r.chunk.id for r in results}


def test_retrieve_respects_top_k(db_session: Session) -> None:
    document = _make_document(db_session)
    for i in range(5):
        _make_chunk(db_session, document, f"Content variant number {i}.")
    db_session.commit()

    [query_embedding] = _embedding_client.embed(["Content variant number 0."])

    results = retrieve(db_session, query_embedding, top_k=2)

    assert len(results) == 2


def test_retrieve_returns_empty_list_with_no_matching_documents(db_session: Session) -> None:
    document = _make_document(db_session, equipment_id="EQ-OTHER")
    _make_chunk(db_session, document, "Some content.")
    db_session.commit()

    [query_embedding] = _embedding_client.embed(["Some content."])

    results = retrieve(db_session, query_embedding, equipment_id="EQ-DOES-NOT-EXIST", top_k=5)

    assert results == []

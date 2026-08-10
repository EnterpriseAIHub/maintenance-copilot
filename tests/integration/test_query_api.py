"""End-to-end tests for POST /query against a real Postgres+pgvector
instance, using the fake embedding/LLM clients (COPILOT_EMBEDDING_PROVIDER
=fake, COPILOT_LLM_PROVIDER=fake — see .env.example / CI config) so no
external API key or network access is required. Documents are ingested
via the real /documents upload endpoint first, matching how this would
actually happen in production.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from fpdf import FPDF

from app.api.main import app

pytestmark = pytest.mark.integration

client = TestClient(app)


def _pdf_bytes(text: str) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 10, text)
    return bytes(pdf.output())


def _upload(text: str, **overrides: str) -> dict:
    data = {
        "title": "Test Manual",
        "source_type": "manual",
        "equipment_id": "EQ-TEST-1",
        **overrides,
    }
    response = client.post(
        "/documents",
        data=data,
        files={"file": ("test.pdf", _pdf_bytes(text), "application/pdf")},
    )
    assert response.status_code == 201
    return response.json()


def test_query_returns_grounded_answer_with_citations() -> None:
    _upload("Bearing housing must be lubricated every 2000 operating hours.")

    response = client.post("/query", json={"question": "How often should I lubricate it?"})

    assert response.status_code == 200
    body = response.json()
    assert body["retrieved_chunk_count"] >= 1
    assert len(body["citations"]) >= 1
    assert "confidence" in body
    assert "chunk_id" in body["citations"][0]


def test_query_with_no_ingested_documents_returns_empty_result() -> None:
    response = client.post(
        "/query",
        json={"question": "Anything about equipment nobody has ever uploaded?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["citations"] == []
    assert body["confidence"] == 0.0


def test_query_filters_by_equipment_id() -> None:
    _upload("Content for the filtering test.", equipment_id="EQ-FILTER-A")

    response = client.post(
        "/query",
        json={"question": "Tell me about equipment.", "equipment_id": "EQ-FILTER-B"},
    )

    assert response.status_code == 200
    assert response.json()["retrieved_chunk_count"] == 0


def test_query_with_empty_question_returns_error_envelope() -> None:
    response = client.post("/query", json={"question": "   "})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

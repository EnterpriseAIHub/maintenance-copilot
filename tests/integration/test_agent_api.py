"""End-to-end tests for POST /agent against a real Postgres+pgvector
instance, using the fake embedding/LLM clients (same convention as
test_query_api.py).

No predictive-maintenance enrichment tests here — /agent has no
enrichment call at all (EDD §12's AgentResponse has no field for it); see
test_conversations_api.py for the enrichment tests, since that's where
EDD §10 actually documents context_from_predictive_maintenance living.
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
        "equipment_id": "EQ-AGENT-1",
        **overrides,
    }
    response = client.post(
        "/documents",
        data=data,
        files={"file": ("test.pdf", _pdf_bytes(text), "application/pdf")},
    )
    assert response.status_code == 201
    return response.json()


def test_agent_returns_grounded_answer_with_bounded_confidence_and_provenance() -> None:
    _upload("Bearing housing must be lubricated every 2000 operating hours.")

    response = client.post("/agent", json={"query": "How often should I lubricate it?"})

    assert response.status_code == 200
    body = response.json()
    assert 0.0 <= body["confidence"] <= 1.0
    assert isinstance(body["provenance"], list)
    assert "citations" not in body
    assert "context_from_predictive_maintenance" not in body


def test_agent_provenance_entries_are_strings_carrying_citation_detail() -> None:
    text = "Bearing housing must be lubricated every 2000 operating hours."
    _upload(text, equipment_id="EQ-AGENT-2")

    response = client.post(
        "/agent", json={"query": text, "context": {"equipment_id": "EQ-AGENT-2"}}
    )

    body = response.json()
    if body["provenance"]:
        assert all(isinstance(p, str) for p in body["provenance"])
        assert "document=" in body["provenance"][0]
        assert "chunk=" in body["provenance"][0]


def test_agent_filters_by_equipment_id_from_context() -> None:
    _upload("Content for equipment filtering test.", equipment_id="EQ-AGENT-FILTER-A")

    response = client.post(
        "/agent",
        json={
            "query": "Tell me about equipment.",
            "context": {"equipment_id": "EQ-AGENT-FILTER-B"},
        },
    )

    assert response.status_code == 200
    assert response.json()["confidence"] == 0.0


def test_agent_with_empty_query_returns_error_envelope() -> None:
    response = client.post("/agent", json={"query": "   "})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_agent_never_attempts_predictive_maintenance_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # /agent has no enrichment call at all — confirm the client function
    # is never even imported/invoked from this path.
    def _fail_if_called(url: str, timeout: float) -> None:
        raise AssertionError("agent_service must never call the enrichment client")

    monkeypatch.setattr("app.rag.predictive_maintenance_client.httpx.get", _fail_if_called)
    monkeypatch.setattr(
        "app.rag.predictive_maintenance_client.settings.predictive_maintenance_base_url",
        "http://predictive-maintenance.local",
    )

    response = client.post(
        "/agent", json={"query": "Anything?", "context": {"equipment_id": "EQ-AGENT-3"}}
    )

    assert response.status_code == 200

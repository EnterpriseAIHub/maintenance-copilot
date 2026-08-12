"""End-to-end tests for /escalations."""

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


def _create_low_confidence_escalation(equipment_id: str = "EQ-ESC-1") -> str:
    """Creates a conversation and asks a question with no matching
    ingested documents, which (per app/rag/orchestrator.py's no-evidence
    fallback) always yields confidence=0.0 — reliably below
    COPILOT_CONFIDENCE_THRESHOLD, so this reliably auto-escalates. Returns
    the assistant message_id.
    """
    conversation = client.post("/conversations", json={"equipment_id": equipment_id}).json()
    client.post(
        f"/conversations/{conversation['id']}/messages",
        json={"question": "Anything about equipment nobody has ever uploaded?"},
    )
    messages = client.get(f"/conversations/{conversation['id']}/messages").json()
    assistant_message = next(m for m in messages if m["role"] == "assistant")
    return assistant_message["id"]


def test_list_escalations_defaults_to_open() -> None:
    message_id = _create_low_confidence_escalation()

    response = client.get("/escalations")

    assert response.status_code == 200
    body = response.json()
    assert any(e["message_id"] == message_id for e in body)
    assert all(e["status"] == "open" for e in body)


def test_list_escalations_rejects_invalid_status() -> None:
    response = client.get("/escalations", params={"status": "bogus"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_get_escalation_returns_snapshot_fields() -> None:
    message_id = _create_low_confidence_escalation(equipment_id="EQ-ESC-2")
    [escalation] = [e for e in client.get("/escalations").json() if e["message_id"] == message_id]

    response = client.get(f"/escalations/{escalation['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["reason"] == "low_confidence"
    assert body["confidence"] == 0.0
    assert body["answer_snapshot"]  # non-empty


def test_get_escalation_404_for_unknown_id() -> None:
    response = client.get("/escalations/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


def test_resolve_moves_escalation_out_of_open_queue() -> None:
    message_id = _create_low_confidence_escalation(equipment_id="EQ-ESC-3")
    [escalation] = [e for e in client.get("/escalations").json() if e["message_id"] == message_id]

    response = client.post(
        f"/escalations/{escalation['id']}/resolve",
        json={"resolution_note": "Reviewed, answer was acceptable."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "resolved"
    assert body["resolution_note"] == "Reviewed, answer was acceptable."
    assert body["resolved_at"] is not None

    open_ids = [e["id"] for e in client.get("/escalations", params={"status": "open"}).json()]
    assert escalation["id"] not in open_ids
    resolved_ids = [
        e["id"] for e in client.get("/escalations", params={"status": "resolved"}).json()
    ]
    assert escalation["id"] in resolved_ids


def test_resolve_404_for_unknown_id() -> None:
    response = client.post(
        "/escalations/00000000-0000-0000-0000-000000000000/resolve",
        json={"resolution_note": "n/a"},
    )

    assert response.status_code == 404

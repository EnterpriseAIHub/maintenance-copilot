"""End-to-end tests for POST /conversations/{cid}/messages/{mid}/feedback."""

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


def _conversation_with_answered_message(
    equipment_id: str = "EQ-FB-1", *, question: str | None = None
) -> tuple[str, str]:
    """Uploads a document, creates a conversation, asks one question, and
    returns (conversation_id, assistant_message_id).

    By default the question text matches the seeded chunk text exactly —
    FakeEmbeddingClient is a deterministic hash of the literal text, not a
    semantic embedding (see its docstring), so an exact match is what
    guarantees a high-confidence, non-auto-escalated answer here. Tests
    that specifically want the auto-escalation path pass a mismatched
    `question` instead.
    """
    text = "Some content."
    client.post(
        "/documents",
        data={"title": "Doc", "source_type": "manual", "equipment_id": equipment_id},
        files={"file": ("t.pdf", _pdf_bytes(text), "application/pdf")},
    )
    conversation = client.post("/conversations", json={"equipment_id": equipment_id}).json()
    client.post(
        f"/conversations/{conversation['id']}/messages",
        json={"question": question or text},
    )
    messages = client.get(f"/conversations/{conversation['id']}/messages").json()
    assistant_message = next(m for m in messages if m["role"] == "assistant")
    return conversation["id"], assistant_message["id"]


def test_submit_positive_feedback_returns_201() -> None:
    conversation_id, message_id = _conversation_with_answered_message()

    response = client.post(
        f"/conversations/{conversation_id}/messages/{message_id}/feedback",
        json={"helpful": True, "comment": "Spot on."},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["helpful"] is True
    assert body["comment"] == "Spot on."
    assert body["message_id"] == message_id


def test_submit_negative_feedback_creates_an_open_escalation() -> None:
    conversation_id, message_id = _conversation_with_answered_message(equipment_id="EQ-FB-2")

    response = client.post(
        f"/conversations/{conversation_id}/messages/{message_id}/feedback",
        json={"helpful": False, "comment": "This is wrong."},
    )
    assert response.status_code == 201

    escalations = client.get("/escalations", params={"status": "open"}).json()
    matching = [e for e in escalations if e["message_id"] == message_id]
    assert len(matching) == 1
    assert matching[0]["reason"] == "negative_feedback"


def test_feedback_404_for_unknown_conversation() -> None:
    response = client.post(
        "/conversations/00000000-0000-0000-0000-000000000000/"
        "messages/00000000-0000-0000-0000-000000000000/feedback",
        json={"helpful": True},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_feedback_404_when_message_belongs_to_a_different_conversation() -> None:
    conversation_id, message_id = _conversation_with_answered_message(equipment_id="EQ-FB-3")
    other_conversation = client.post("/conversations", json={}).json()

    response = client.post(
        f"/conversations/{other_conversation['id']}/messages/{message_id}/feedback",
        json={"helpful": True},
    )

    assert response.status_code == 404

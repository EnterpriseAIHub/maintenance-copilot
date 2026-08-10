"""End-to-end tests for the /conversations endpoints against a real
Postgres instance, using the fake embedding/LLM clients (same convention
as tests/integration/test_query_api.py). SSE responses are consumed as
plain text and parsed by hand, matching the `event: ...\\ndata: ...\\n\\n`
format app/api/routes/conversations.py writes.
"""

from __future__ import annotations

import json

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
        "equipment_id": "EQ-CONV-1",
        **overrides,
    }
    response = client.post(
        "/documents",
        data=data,
        files={"file": ("test.pdf", _pdf_bytes(text), "application/pdf")},
    )
    assert response.status_code == 201
    return response.json()


def _parse_sse_events(text: str) -> list[dict]:
    events = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        event_line, data_line = block.split("\n", 1)
        event_name = event_line.removeprefix("event: ")
        data = json.loads(data_line.removeprefix("data: "))
        events.append({"event": event_name, "data": data})
    return events


def _create_conversation(**overrides: str | None) -> dict:
    response = client.post("/conversations", json=overrides)
    assert response.status_code == 201
    return response.json()


def test_create_conversation_returns_201_with_fields() -> None:
    body = _create_conversation(equipment_id="EQ-1", plant_id="PLANT-A")

    assert body["equipment_id"] == "EQ-1"
    assert body["plant_id"] == "PLANT-A"
    assert body["started_by"] == "local-dev-user"
    assert "id" in body


def test_get_conversation_returns_it() -> None:
    created = _create_conversation()

    response = client.get(f"/conversations/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_conversation_404_for_unknown_id() -> None:
    response = client.get("/conversations/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_post_message_streams_progress_events_and_final_answer() -> None:
    _upload(
        "Bearing housing must be lubricated every 2000 operating hours.",
        equipment_id="EQ-CONV-2",
    )
    conversation = _create_conversation(equipment_id="EQ-CONV-2")

    response = client.post(
        f"/conversations/{conversation['id']}/messages",
        json={"question": "How often should I lubricate it?"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse_events(response.text)
    assert [e["event"] for e in events] == ["retrieving", "generating", "done"]

    final = events[-1]["data"]
    assert final["role"] == "assistant"
    assert len(final["citations"]) >= 1
    assert final["confidence"] > 0.0


def test_post_message_404_for_unknown_conversation() -> None:
    response = client.post(
        "/conversations/00000000-0000-0000-0000-000000000000/messages",
        json={"question": "Anything?"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_post_message_with_empty_question_returns_error_envelope() -> None:
    conversation = _create_conversation()

    response = client.post(
        f"/conversations/{conversation['id']}/messages",
        json={"question": "   "},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_get_messages_returns_full_history_after_a_turn() -> None:
    _upload(
        "Vibration alarm threshold is 7.1 mm/s RMS.",
        equipment_id="EQ-CONV-3",
    )
    conversation = _create_conversation(equipment_id="EQ-CONV-3")
    client.post(
        f"/conversations/{conversation['id']}/messages",
        json={"question": "What is the vibration alarm threshold?"},
    )

    response = client.get(f"/conversations/{conversation['id']}/messages")

    assert response.status_code == 200
    messages = response.json()
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "What is the vibration alarm threshold?"
    assert len(messages[1]["citations"]) >= 1


def test_get_messages_404_for_unknown_conversation() -> None:
    response = client.get("/conversations/00000000-0000-0000-0000-000000000000/messages")

    assert response.status_code == 404

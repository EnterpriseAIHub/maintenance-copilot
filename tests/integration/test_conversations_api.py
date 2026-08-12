"""End-to-end tests for the /conversations endpoints against a real
Postgres instance, using the fake embedding/LLM clients (same convention
as tests/integration/test_query_api.py). SSE responses are consumed as
plain text and parsed by hand, matching the `event: ...\\ndata: ...\\n\\n`
format app/api/routes/conversations.py writes.
"""

from __future__ import annotations

import json

import httpx
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
    # Key is always present on the "done" event (EDD §10: "present only if
    # fetched successfully" describes the *value*, not the key) — None by
    # default here since no predictive-maintenance base URL is configured.
    assert final["context_from_predictive_maintenance"] is None


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
    # Deliberately not part of the persisted/history shape — see
    # app/services/conversation_service.py's module docstring on why a
    # time-sensitive risk snapshot isn't re-shown on every history read.
    assert "context_from_predictive_maintenance" not in messages[1]


def test_get_messages_404_for_unknown_conversation() -> None:
    response = client.get("/conversations/00000000-0000-0000-0000-000000000000/messages")

    assert response.status_code == 404


# --- Predictive-maintenance risk-context enrichment (EDD FR6, §10) ---


def test_message_omits_predictive_maintenance_context_when_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.rag.predictive_maintenance_client.settings.predictive_maintenance_base_url", None
    )
    _upload("Some content.", equipment_id="EQ-CONV-PM-1")
    conversation = _create_conversation(equipment_id="EQ-CONV-PM-1")

    response = client.post(
        f"/conversations/{conversation['id']}/messages", json={"question": "Some content."}
    )

    events = _parse_sse_events(response.text)
    assert events[-1]["data"]["context_from_predictive_maintenance"] is None


def test_message_includes_predictive_maintenance_context_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {
                "failure_probability": 0.82,
                "model_version": "v1.3.0",
                "source": "predictive-maintenance:/equipment/EQ-CONV-PM-2/risk",
            }

    monkeypatch.setattr(
        "app.rag.predictive_maintenance_client.settings.predictive_maintenance_base_url",
        "http://predictive-maintenance.local",
    )
    monkeypatch.setattr(
        "app.rag.predictive_maintenance_client.httpx.get",
        lambda url, timeout: _FakeResponse(),
    )
    _upload("Some content.", equipment_id="EQ-CONV-PM-2")
    conversation = _create_conversation(equipment_id="EQ-CONV-PM-2")

    response = client.post(
        f"/conversations/{conversation['id']}/messages", json={"question": "Some content."}
    )

    events = _parse_sse_events(response.text)
    assert events[-1]["data"]["context_from_predictive_maintenance"] == {
        "failure_probability": 0.82,
        "model_version": "v1.3.0",
        "source": "predictive-maintenance:/equipment/EQ-CONV-PM-2/risk",
    }


def test_message_degrades_gracefully_when_predictive_maintenance_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.rag.predictive_maintenance_client.settings.predictive_maintenance_base_url",
        "http://predictive-maintenance.local",
    )

    def _raise(url: str, timeout: float) -> None:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("app.rag.predictive_maintenance_client.httpx.get", _raise)
    _upload("Some content.", equipment_id="EQ-CONV-PM-3")
    conversation = _create_conversation(equipment_id="EQ-CONV-PM-3")

    response = client.post(
        f"/conversations/{conversation['id']}/messages", json={"question": "Some content."}
    )

    # The whole point: an unreachable sibling must never break the
    # conversation turn, just omit the enrichment field.
    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["context_from_predictive_maintenance"] is None
    assert events[-1]["data"]["content"]


def test_message_without_conversation_equipment_id_never_attempts_enrichment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.rag.predictive_maintenance_client.settings.predictive_maintenance_base_url",
        "http://predictive-maintenance.local",
    )

    def _fail_if_called(url: str, timeout: float) -> None:
        raise AssertionError(
            "enrichment should not be attempted without a conversation equipment_id"
        )

    monkeypatch.setattr("app.rag.predictive_maintenance_client.httpx.get", _fail_if_called)
    conversation = _create_conversation()  # no equipment_id

    response = client.post(
        f"/conversations/{conversation['id']}/messages", json={"question": "Anything at all?"}
    )

    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    assert events[-1]["data"]["context_from_predictive_maintenance"] is None

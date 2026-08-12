"""Integration tests for app/services/escalation_service.py and the
auto-escalation trigger wired into
app/services/conversation_service.py::generate_answer_stream().
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.data.models.chunk import Chunk
from app.data.models.document import Document
from app.data.models.message import Message
from app.rag.embedding_client import FakeEmbeddingClient
from app.services.conversation_service import ConversationService
from app.services.errors import NotFoundError
from app.services.escalation_service import EscalationService

pytestmark = pytest.mark.integration

_embedding_client = FakeEmbeddingClient()


def _seed_document_with_chunk(db: Session, *, text: str, equipment_id: str = "EQ-1") -> Chunk:
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


def _make_message(db: Session, *, conversation_id, role: str, confidence: float | None) -> Message:
    message = Message(
        id=uuid4(),
        conversation_id=conversation_id,
        role=role,
        content="some content",
        confidence=confidence,
        retrieved_chunk_count=1 if confidence is not None else None,
    )
    db.add(message)
    db.commit()
    return message


# --- EscalationService unit-of-behavior tests (still integration-tier: needs a real DB) ---


def test_escalate_if_needed_creates_an_open_escalation(db_session: Session) -> None:
    conversation_service = ConversationService(db_session)
    conversation = conversation_service.create_conversation(
        equipment_id=None, plant_id=None, started_by="tester"
    )
    message = _make_message(
        db_session, conversation_id=conversation.id, role="assistant", confidence=0.2
    )
    service = EscalationService(db_session)

    escalation = service.escalate_if_needed(message, reason="low_confidence")
    db_session.commit()

    assert escalation is not None
    assert escalation.status == "open"
    assert escalation.reason == "low_confidence"
    assert escalation.confidence == pytest.approx(0.2)
    assert escalation.conversation_id == conversation.id


def test_escalate_if_needed_is_a_noop_for_user_messages(db_session: Session) -> None:
    conversation_service = ConversationService(db_session)
    conversation = conversation_service.create_conversation(
        equipment_id=None, plant_id=None, started_by="tester"
    )
    message = _make_message(
        db_session, conversation_id=conversation.id, role="user", confidence=None
    )
    service = EscalationService(db_session)

    result = service.escalate_if_needed(message, reason="low_confidence")

    assert result is None


def test_escalate_if_needed_does_not_duplicate_an_open_escalation(db_session: Session) -> None:
    conversation_service = ConversationService(db_session)
    conversation = conversation_service.create_conversation(
        equipment_id=None, plant_id=None, started_by="tester"
    )
    message = _make_message(
        db_session, conversation_id=conversation.id, role="assistant", confidence=0.1
    )
    service = EscalationService(db_session)

    first = service.escalate_if_needed(message, reason="low_confidence")
    db_session.commit()
    second = service.escalate_if_needed(message, reason="negative_feedback")
    db_session.commit()

    assert first is not None
    assert second is not None
    assert first.id == second.id  # same row, not a new one
    assert len(service.list_escalations(status="open")) == 1


def test_resolve_marks_escalation_resolved_with_note(db_session: Session) -> None:
    conversation_service = ConversationService(db_session)
    conversation = conversation_service.create_conversation(
        equipment_id=None, plant_id=None, started_by="tester"
    )
    message = _make_message(
        db_session, conversation_id=conversation.id, role="assistant", confidence=0.1
    )
    service = EscalationService(db_session)
    escalation = service.escalate_if_needed(message, reason="low_confidence")
    db_session.commit()

    resolved = service.resolve(escalation.id, resolution_note="Confirmed correct, false alarm.")

    assert resolved.status == "resolved"
    assert resolved.resolution_note == "Confirmed correct, false alarm."
    assert resolved.resolved_at is not None
    assert len(service.list_escalations(status="open")) == 0
    assert len(service.list_escalations(status="resolved")) == 1


def test_get_escalation_raises_not_found_for_unknown_id(db_session: Session) -> None:
    service = EscalationService(db_session)

    with pytest.raises(NotFoundError):
        service.get_escalation(uuid4())


# --- Auto-escalation trigger wired into ConversationService ---


def test_low_confidence_answer_auto_escalates(db_session: Session) -> None:
    # No ingested documents at all -> retrieval returns nothing ->
    # orchestrator.answer_question() returns confidence=0.0 (see
    # app/rag/orchestrator.py's no-evidence fallback), which is below the
    # default COPILOT_CONFIDENCE_THRESHOLD=0.55 regardless of environment.
    service = ConversationService(db_session)
    conversation = service.create_conversation(
        equipment_id=None, plant_id=None, started_by="tester"
    )

    events = list(
        service.generate_answer_stream(conversation, "Anything about equipment nobody uploaded?")
    )

    assert events[-1]["data"]["escalated"] is True
    escalation_service = EscalationService(db_session)
    open_escalations = escalation_service.list_escalations(status="open")
    assert len(open_escalations) == 1
    assert open_escalations[0].reason == "low_confidence"
    assert open_escalations[0].conversation_id == conversation.id


def test_high_confidence_answer_does_not_auto_escalate(db_session: Session) -> None:
    # FakeEmbeddingClient is a deterministic hash of the literal text, not
    # a semantic embedding (see its docstring) — using the exact same
    # string for the seeded chunk and the question is what guarantees
    # near-1.0 cosine similarity here, not semantic relatedness.
    text = "Lubricate bearing every 2000 hours."
    _seed_document_with_chunk(db_session, text=text)
    service = ConversationService(db_session)
    conversation = service.create_conversation(
        equipment_id="EQ-1", plant_id=None, started_by="tester"
    )

    events = list(service.generate_answer_stream(conversation, text))

    assert events[-1]["data"]["confidence"] > 0.55
    assert events[-1]["data"]["escalated"] is False
    escalation_service = EscalationService(db_session)
    assert escalation_service.list_escalations(status="open") == []

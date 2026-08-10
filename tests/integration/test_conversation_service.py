"""Integration tests for app/services/conversation_service.py against a
real Postgres instance, using the fake embedding/LLM clients so the RAG
pipeline underneath is deterministic — see their docstrings.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.data.models.chunk import Chunk
from app.data.models.document import Document
from app.rag.embedding_client import FakeEmbeddingClient
from app.services.conversation_service import ConversationService
from app.services.errors import NotFoundError

pytestmark = pytest.mark.integration

_embedding_client = FakeEmbeddingClient()


def _seed_document_with_chunk(db: Session, *, text: str) -> Chunk:
    document = Document(
        id=uuid4(),
        title="Test Doc",
        source_type="manual",
        equipment_id="EQ-1",
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


def test_create_conversation_persists_and_returns_it(db_session: Session) -> None:
    service = ConversationService(db_session)

    conversation = service.create_conversation(
        equipment_id="EQ-1", plant_id="PLANT-A", started_by="tester"
    )

    assert conversation.id is not None
    fetched = service.get_conversation(conversation.id)
    assert fetched.equipment_id == "EQ-1"
    assert fetched.plant_id == "PLANT-A"
    assert fetched.started_by == "tester"


def test_get_conversation_raises_not_found_for_unknown_id(db_session: Session) -> None:
    service = ConversationService(db_session)

    with pytest.raises(NotFoundError):
        service.get_conversation(uuid4())


def test_generate_answer_stream_persists_user_and_assistant_messages(
    db_session: Session,
) -> None:
    _seed_document_with_chunk(db_session, text="Lubricate bearing every 2000 hours.")
    service = ConversationService(db_session)
    conversation = service.create_conversation(
        equipment_id="EQ-1", plant_id=None, started_by="tester"
    )

    events = list(
        service.generate_answer_stream(conversation, "How often should the bearing be lubricated?")
    )

    event_names = [e["event"] for e in events]
    assert event_names == ["retrieving", "generating", "done"]

    done_data = events[-1]["data"]
    assert done_data["role"] == "assistant"
    assert len(done_data["citations"]) == 1
    assert done_data["confidence"] > 0.0

    history = service.list_messages(conversation.id)
    assert [m.role for m in history] == ["user", "assistant"]
    assert history[0].content == "How often should the bearing be lubricated?"
    assert len(history[1].citations) == 1


def test_generate_answer_stream_with_no_documents_still_persists_both_turns(
    db_session: Session,
) -> None:
    service = ConversationService(db_session)
    conversation = service.create_conversation(
        equipment_id=None, plant_id=None, started_by="tester"
    )

    events = list(
        service.generate_answer_stream(conversation, "Anything about equipment nobody uploaded?")
    )

    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["citations"] == []
    assert events[-1]["data"]["confidence"] == 0.0

    history = service.list_messages(conversation.id)
    assert len(history) == 2


def test_conversation_history_is_included_in_second_turn_prompt(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_document_with_chunk(db_session, text="Lubricate bearing every 2000 hours.")
    service = ConversationService(db_session)
    conversation = service.create_conversation(
        equipment_id="EQ-1", plant_id=None, started_by="tester"
    )

    list(service.generate_answer_stream(conversation, "How often should I lubricate it?"))

    captured_history = []
    from app.rag import orchestrator as orchestrator_module

    original = orchestrator_module.answer_question

    def _spy(*args, **kwargs):
        captured_history.append(kwargs.get("conversation_history"))
        return original(*args, **kwargs)

    monkeypatch.setattr("app.services.conversation_service.answer_question", _spy)

    list(service.generate_answer_stream(conversation, "What about the seal instead?"))

    assert len(captured_history) == 1
    [history] = captured_history
    assert history is not None
    assert len(history) == 1
    assert history[0].question == "How often should I lubricate it?"


def test_conversation_history_limit_caps_turns_passed_to_orchestrator(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.services.conversation_service.settings.conversation_history_limit", 2)
    _seed_document_with_chunk(db_session, text="Lubricate bearing every 2000 hours.")
    service = ConversationService(db_session)
    conversation = service.create_conversation(
        equipment_id="EQ-1", plant_id=None, started_by="tester"
    )

    for i in range(4):
        list(service.generate_answer_stream(conversation, f"Question number {i}?"))

    history = service._load_conversation_history(conversation.id)

    assert len(history) == 2
    assert history[0].question == "Question number 2?"
    assert history[1].question == "Question number 3?"

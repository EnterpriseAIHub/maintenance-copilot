from __future__ import annotations

from uuid import uuid4

from app.data.models.chunk import Chunk
from app.rag.prompt_builder import ConversationTurn, build_prompt
from app.rag.retriever import RetrievedChunk


def _make_retrieved_chunk(
    *, text: str, section_title: str | None = None, page_number: int | None = None
) -> RetrievedChunk:
    chunk = Chunk(
        id=uuid4(),
        document_id=uuid4(),
        chunk_index=0,
        text=text,
        token_count=10,
        embedding=[0.0],
        chunk_metadata={"section_title": section_title, "page_number": page_number},
    )
    return RetrievedChunk(chunk=chunk, similarity=0.9)


def test_system_prompt_instructs_context_only_answering() -> None:
    system_prompt, _ = build_prompt("question", [_make_retrieved_chunk(text="content")])

    assert "ONLY" in system_prompt
    assert "provide_answer" in system_prompt


def test_user_prompt_includes_question_and_chunk_id() -> None:
    retrieved = _make_retrieved_chunk(text="Lubricate every 2000 hours.")

    _, user_prompt = build_prompt("How often should I lubricate the pump?", [retrieved])

    assert "How often should I lubricate the pump?" in user_prompt
    assert str(retrieved.chunk.id) in user_prompt
    assert "Lubricate every 2000 hours." in user_prompt


def test_user_prompt_includes_section_and_page_when_present() -> None:
    retrieved = _make_retrieved_chunk(
        text="content", section_title="LUBRICATION SCHEDULE", page_number=3
    )

    _, user_prompt = build_prompt("question", [retrieved])

    assert "section: LUBRICATION SCHEDULE" in user_prompt
    assert "page: 3" in user_prompt


def test_user_prompt_omits_missing_section_and_page() -> None:
    retrieved = _make_retrieved_chunk(text="content")

    _, user_prompt = build_prompt("question", [retrieved])

    assert "section:" not in user_prompt
    assert "page:" not in user_prompt


def test_multiple_chunks_are_separated() -> None:
    retrieved = [
        _make_retrieved_chunk(text="first chunk"),
        _make_retrieved_chunk(text="second chunk"),
    ]

    _, user_prompt = build_prompt("question", retrieved)

    assert "first chunk" in user_prompt
    assert "second chunk" in user_prompt
    assert user_prompt.count("---") == 1


def test_no_conversation_history_produces_identical_prompt_to_omitting_it() -> None:
    # Regression guard for the Phase 4 additive change: passing
    # conversation_history=None (the default) must be byte-for-byte
    # identical to not passing the parameter at all, since POST /query
    # and every Phase 3 test call build_prompt() without it.
    retrieved = [_make_retrieved_chunk(text="content")]

    without_param = build_prompt("question", retrieved)
    with_none = build_prompt("question", retrieved, conversation_history=None)

    assert without_param == with_none


def test_empty_conversation_history_list_omits_history_section() -> None:
    retrieved = [_make_retrieved_chunk(text="content")]

    _, user_prompt = build_prompt("question", retrieved, conversation_history=[])

    assert "Conversation so far" not in user_prompt


def test_conversation_history_is_rendered_before_context() -> None:
    retrieved = [_make_retrieved_chunk(text="content")]
    history = [
        ConversationTurn(
            question="How often should P-101 be lubricated?", answer="Every 2000 hours."
        )
    ]

    _, user_prompt = build_prompt(
        "What about the seal instead?", retrieved, conversation_history=history
    )

    assert "Conversation so far" in user_prompt
    assert "Q: How often should P-101 be lubricated?" in user_prompt
    assert "A: Every 2000 hours." in user_prompt
    assert user_prompt.index("Conversation so far") < user_prompt.index("Context:")


def test_multiple_conversation_turns_all_appear_in_order() -> None:
    retrieved = [_make_retrieved_chunk(text="content")]
    history = [
        ConversationTurn(question="Q1", answer="A1"),
        ConversationTurn(question="Q2", answer="A2"),
    ]

    _, user_prompt = build_prompt("Q3", retrieved, conversation_history=history)

    assert user_prompt.index("Q1") < user_prompt.index("Q2") < user_prompt.index("Q3")


def test_system_prompt_mentions_history_is_not_a_citable_source() -> None:
    system_prompt, _ = build_prompt("question", [_make_retrieved_chunk(text="content")])

    assert "not a source of facts to cite" in system_prompt

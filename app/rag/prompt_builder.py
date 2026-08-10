"""Prompt builder.

Assembles the system prompt (answering rules) and user prompt (numbered
context chunks + the question) passed to app/rag/llm_client.py. Each
context block is labeled with its chunk_id so the model can cite it back
via the `provide_answer` tool's `cited_chunk_ids` field — see
llm_client.py's module docstring for the citation contract this depends
on.

`conversation_history` (Phase 4) is optional and additive: when present,
prior turns are rendered into the user prompt so the model can resolve
follow-up questions ("what about the seal instead?") using conversational
context — but retrieval itself (app/rag/orchestrator.py::answer_question)
still embeds only the current question, never the history. Mixing history
into the text that gets embedded would pull retrieval off the actual
current information need; keeping history purely a prompt-context concern
avoids that while still giving the model what it needs to answer
naturally. Every existing call site that doesn't pass this parameter
(POST /query) is completely unaffected.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.rag.retriever import RetrievedChunk

_SYSTEM_PROMPT = (
    "You are a maintenance knowledge assistant for industrial equipment. Answer "
    "the technician's question using ONLY the context chunks provided below — "
    "never rely on outside knowledge, even if you're confident it's correct. "
    "Every fact you state must be traceable to at least one chunk_id you cite. "
    "If the context doesn't contain enough information to answer confidently, "
    "say so plainly instead of guessing, and cite no chunks. If earlier turns of "
    "the conversation are provided, use them only to understand what the "
    "technician is referring to (e.g. a follow-up question) — they are not a "
    "source of facts to cite. You must call the provide_answer tool exactly once."
)


@dataclass(frozen=True)
class ConversationTurn:
    question: str
    answer: str


def build_prompt(
    question: str,
    retrieved: list[RetrievedChunk],
    *,
    conversation_history: list[ConversationTurn] | None = None,
) -> tuple[str, str]:
    """Returns (system_prompt, user_prompt) for one question."""
    parts = []
    if conversation_history:
        parts.append(_format_history(conversation_history))
    context_blocks = [_format_chunk(r) for r in retrieved]
    parts.append("Context:\n\n" + "\n\n---\n\n".join(context_blocks))
    parts.append(f"Question: {question}")
    user_prompt = "\n\n".join(parts)
    return _SYSTEM_PROMPT, user_prompt


def _format_history(conversation_history: list[ConversationTurn]) -> str:
    turns = "\n\n".join(f"Q: {t.question}\nA: {t.answer}" for t in conversation_history)
    return f"Conversation so far:\n\n{turns}"


def _format_chunk(retrieved: RetrievedChunk) -> str:
    chunk = retrieved.chunk
    header_parts = [f"chunk_id: {chunk.id}"]

    section_title = chunk.chunk_metadata.get("section_title")
    if section_title:
        header_parts.append(f"section: {section_title}")

    page_number = chunk.chunk_metadata.get("page_number")
    if page_number is not None:
        header_parts.append(f"page: {page_number}")

    header = " | ".join(header_parts)
    return f"[{header}]\n{chunk.text}"

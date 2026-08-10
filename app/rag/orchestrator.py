"""RAG orchestrator.

The single function tying retrieval, prompt assembly, the LLM call,
citation extraction, and confidence scoring together. Phase 3's stateless
POST /query endpoint is the only caller today; Phase 4's
/conversations/{id}/messages and Phase 6's /agent are expected to call
this same function — the same "one code path" pattern already applied to
app/ingestion/pipeline.py::run_ingestion for upload vs. re-index (see
PROJECT_PROGRESS.md §3).

Phase 4 adds one optional, additive parameter: `conversation_history`.
Retrieval below still embeds `question` alone — history is threaded
through to app/rag/prompt_builder.py for LLM prompt context only, never
into what gets embedded for the vector search. See prompt_builder.py's
module docstring for why that split matters. Every existing call site
(POST /query, all Phase 3 tests) that omits this parameter is completely
unaffected.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.rag.citation_extractor import Citation, extract_citations
from app.rag.confidence_scorer import score_confidence
from app.rag.embedding_client import EmbeddingClient, get_embedding_client
from app.rag.llm_client import LLMClient, get_llm_client
from app.rag.prompt_builder import ConversationTurn, build_prompt
from app.rag.retriever import retrieve

_NO_EVIDENCE_ANSWER = "I don't have any ingested documents that address this question."


@dataclass(frozen=True)
class RagAnswer:
    answer: str
    citations: list[Citation]
    confidence: float
    retrieved_chunk_count: int


def answer_question(
    db: Session,
    question: str,
    *,
    equipment_id: str | None = None,
    plant_id: str | None = None,
    embedding_client: EmbeddingClient | None = None,
    llm_client: LLMClient | None = None,
    conversation_history: list[ConversationTurn] | None = None,
) -> RagAnswer:
    """Answers one question end-to-end against the ingested corpus.

    `embedding_client`/`llm_client` are optional overrides (used by
    tests/the eval harness to pin specific provider instances); callers
    that don't pass them get whatever app/config/settings.py currently
    configures. `conversation_history` is optional prior-turn context for
    the LLM prompt only — see module docstring.
    """
    embedding_client = embedding_client or get_embedding_client()
    llm_client = llm_client or get_llm_client()

    [query_embedding] = embedding_client.embed([question])
    retrieved = retrieve(db, query_embedding, equipment_id=equipment_id, plant_id=plant_id)

    if not retrieved:
        return RagAnswer(
            answer=_NO_EVIDENCE_ANSWER, citations=[], confidence=0.0, retrieved_chunk_count=0
        )

    system_prompt, user_prompt = build_prompt(
        question, retrieved, conversation_history=conversation_history
    )
    chunk_ids = [str(r.chunk.id) for r in retrieved]
    llm_answer = llm_client.generate_answer(system_prompt, user_prompt, chunk_ids)

    citations = extract_citations(llm_answer.cited_chunk_ids, retrieved)
    confidence = score_confidence(retrieved, citations, llm_answer.self_rated_confidence)

    return RagAnswer(
        answer=llm_answer.answer_text,
        citations=citations,
        confidence=confidence,
        retrieved_chunk_count=len(retrieved),
    )

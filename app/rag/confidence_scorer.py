"""Confidence scoring.

Combines two independent signals into one 0-1 confidence score, compared
against COPILOT_CONFIDENCE_THRESHOLD by callers deciding whether to
surface an answer as-is or flag it (e.g. Phase 5's auto-escalation):

- Retrieval confidence: mean cosine similarity of the chunks the model
  actually cited. A model can only be as right as the evidence it was
  given — this says nothing about whether the model used that evidence
  correctly, which is why it's not the whole score.
- Self-rated confidence: the LLM's own stated confidence that its answer
  is fully supported by what it cited (see app/rag/llm_client.py). LLM
  self-ratings are well known to be poorly calibrated on their own, which
  is why this isn't the whole score either.

An answer with zero citations is scored 0 outright, regardless of
self-rated confidence — an ungrounded self-rating isn't evidence of
anything.
"""

from __future__ import annotations

from app.rag.citation_extractor import Citation
from app.rag.retriever import RetrievedChunk

RETRIEVAL_WEIGHT = 0.5
SELF_RATING_WEIGHT = 0.5


def score_confidence(
    retrieved: list[RetrievedChunk],
    citations: list[Citation],
    self_rated_confidence: float,
) -> float:
    if not citations:
        return 0.0

    cited_ids = {c.chunk_id for c in citations}
    cited_similarities = [r.similarity for r in retrieved if r.chunk.id in cited_ids]
    retrieval_component = (
        sum(cited_similarities) / len(cited_similarities) if cited_similarities else 0.0
    )

    score = RETRIEVAL_WEIGHT * _clamp(retrieval_component) + SELF_RATING_WEIGHT * _clamp(
        self_rated_confidence
    )
    return round(_clamp(score), 4)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))

from __future__ import annotations

from uuid import uuid4

import pytest

from app.data.models.chunk import Chunk
from app.rag.citation_extractor import Citation
from app.rag.confidence_scorer import score_confidence
from app.rag.retriever import RetrievedChunk


def _make_retrieved_chunk(*, similarity: float) -> RetrievedChunk:
    chunk = Chunk(
        id=uuid4(),
        document_id=uuid4(),
        chunk_index=0,
        text="text",
        token_count=10,
        embedding=[0.0],
        chunk_metadata={},
    )
    return RetrievedChunk(chunk=chunk, similarity=similarity)


def _make_citation(retrieved: RetrievedChunk) -> Citation:
    return Citation(
        chunk_id=retrieved.chunk.id,
        document_id=retrieved.chunk.document_id,
        section_title=None,
        page_number=None,
        snippet="text",
    )


def test_zero_citations_scores_zero_regardless_of_self_rating() -> None:
    retrieved = [_make_retrieved_chunk(similarity=0.95)]

    assert score_confidence(retrieved, [], self_rated_confidence=0.99) == 0.0


def test_high_similarity_and_high_self_rating_scores_high() -> None:
    retrieved = [_make_retrieved_chunk(similarity=0.95)]
    citations = [_make_citation(retrieved[0])]

    score = score_confidence(retrieved, citations, self_rated_confidence=0.95)

    assert score > 0.9


def test_low_similarity_pulls_score_down_even_with_high_self_rating() -> None:
    retrieved = [_make_retrieved_chunk(similarity=0.1)]
    citations = [_make_citation(retrieved[0])]

    score = score_confidence(retrieved, citations, self_rated_confidence=1.0)

    # Self-rating alone (weight 0.5) can't carry the score above ~0.5 when
    # retrieval similarity is this low.
    assert score < 0.6


def test_only_cited_chunks_contribute_to_retrieval_component() -> None:
    cited = _make_retrieved_chunk(similarity=0.9)
    uncited = _make_retrieved_chunk(similarity=0.1)
    citations = [_make_citation(cited)]

    score = score_confidence([cited, uncited], citations, self_rated_confidence=0.9)

    # If the uncited low-similarity chunk were mistakenly included in the
    # average, this would be pulled well below 0.85.
    assert score >= 0.85


@pytest.mark.parametrize("self_rated_confidence", [-1.0, 2.0])
def test_out_of_range_self_rating_is_clamped(self_rated_confidence: float) -> None:
    retrieved = [_make_retrieved_chunk(similarity=0.5)]
    citations = [_make_citation(retrieved[0])]

    score = score_confidence(retrieved, citations, self_rated_confidence=self_rated_confidence)

    assert 0.0 <= score <= 1.0

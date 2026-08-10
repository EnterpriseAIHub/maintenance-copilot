from __future__ import annotations

from uuid import uuid4

from app.data.models.chunk import Chunk
from app.rag.citation_extractor import extract_citations
from app.rag.retriever import RetrievedChunk


def _make_retrieved_chunk(*, text: str = "some chunk text") -> RetrievedChunk:
    chunk = Chunk(
        id=uuid4(),
        document_id=uuid4(),
        chunk_index=0,
        text=text,
        token_count=10,
        embedding=[0.0],
        chunk_metadata={"section_title": "A SECTION", "page_number": 2},
    )
    return RetrievedChunk(chunk=chunk, similarity=0.9)


def test_resolves_a_valid_cited_chunk_id() -> None:
    retrieved = _make_retrieved_chunk()

    citations = extract_citations([str(retrieved.chunk.id)], [retrieved])

    assert len(citations) == 1
    citation = citations[0]
    assert citation.chunk_id == retrieved.chunk.id
    assert citation.document_id == retrieved.chunk.document_id
    assert citation.section_title == "A SECTION"
    assert citation.page_number == 2


def test_drops_a_hallucinated_chunk_id_not_in_retrieved_set() -> None:
    retrieved = _make_retrieved_chunk()

    citations = extract_citations([str(uuid4())], [retrieved])

    assert citations == []


def test_deduplicates_repeated_citations_of_the_same_chunk() -> None:
    retrieved = _make_retrieved_chunk()
    chunk_id = str(retrieved.chunk.id)

    citations = extract_citations([chunk_id, chunk_id], [retrieved])

    assert len(citations) == 1


def test_empty_cited_ids_produce_no_citations() -> None:
    retrieved = _make_retrieved_chunk()

    assert extract_citations([], [retrieved]) == []


def test_snippet_is_truncated_for_long_chunk_text() -> None:
    long_text = "word " * 200
    retrieved = _make_retrieved_chunk(text=long_text)

    [citation] = extract_citations([str(retrieved.chunk.id)], [retrieved])

    assert len(citation.snippet) < len(long_text)
    assert citation.snippet.endswith("…")


def test_snippet_is_not_truncated_for_short_chunk_text() -> None:
    retrieved = _make_retrieved_chunk(text="short text")

    [citation] = extract_citations([str(retrieved.chunk.id)], [retrieved])

    assert citation.snippet == "short text"

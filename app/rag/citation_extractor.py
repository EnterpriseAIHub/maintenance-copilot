"""Citation extraction.

Resolves the chunk_ids an LLMAnswer claims to have cited back into
Citation records with enough context (document, section, page, a short
text snippet) to show a technician exactly where an answer came from.

Any cited chunk_id that doesn't correspond to a chunk that was actually
retrieved is dropped rather than trusted — a model can report an id that
merely looks plausible, and a citation pointing at content the retriever
never actually surfaced would be worse than no citation at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.rag.retriever import RetrievedChunk

_SNIPPET_MAX_CHARS = 240


@dataclass(frozen=True)
class Citation:
    chunk_id: UUID
    document_id: UUID
    section_title: str | None
    page_number: int | None
    snippet: str


def extract_citations(
    cited_chunk_ids: list[str], retrieved: list[RetrievedChunk]
) -> list[Citation]:
    by_id = {str(r.chunk.id): r.chunk for r in retrieved}
    citations: list[Citation] = []
    seen: set[str] = set()

    for raw_id in cited_chunk_ids:
        if raw_id in seen:
            continue
        chunk = by_id.get(raw_id)
        if chunk is None:
            # Hallucinated/invalid citation — dropped, not trusted. See
            # module docstring.
            continue
        seen.add(raw_id)
        citations.append(
            Citation(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                section_title=chunk.chunk_metadata.get("section_title"),
                page_number=chunk.chunk_metadata.get("page_number"),
                snippet=_snippet(chunk.text),
            )
        )
    return citations


def _snippet(text: str) -> str:
    text = text.strip()
    if len(text) <= _SNIPPET_MAX_CHARS:
        return text
    return text[:_SNIPPET_MAX_CHARS].rsplit(" ", 1)[0] + "…"

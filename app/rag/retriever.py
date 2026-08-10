"""Retriever.

Vector similarity search against `Chunk.embedding` using pgvector's cosine
distance operator — the ivfflat index created in migration 0002 uses
`vector_cosine_ops` (see PROJECT_PROGRESS.md §4), so cosine distance is
the operator that index actually accelerates; a different distance
function here would silently fall back to a sequential scan.

Queries are embedded with the same EmbeddingClient used for ingestion
(see app/rag/embedding_client.py's docstring on avoiding ingest/query
skew) — this module receives an already-computed query embedding rather
than an EmbeddingClient itself, so it stays a pure data-access concern.

equipment_id/plant_id filters are applied against `Document`, not against
the duplicate copy written into `Chunk.chunk_metadata` at ingestion time
(see app/ingestion/pipeline.py) — the document table already has
`ix_document_equipment_status` covering equipment_id, and filtering there
avoids a JSONB text-extraction comparator for no benefit.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.data.models.chunk import Chunk
from app.data.models.document import Document


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: Chunk
    similarity: float  # 1 - cosine_distance; higher is more similar


def retrieve(
    db: Session,
    query_embedding: list[float],
    *,
    equipment_id: str | None = None,
    plant_id: str | None = None,
    top_k: int | None = None,
) -> list[RetrievedChunk]:
    """Returns up to top_k chunks closest to query_embedding, most similar first.

    Only chunks belonging to `active` documents are eligible — a document
    that's still processing, failed, or archived shouldn't surface as
    retrieved evidence even though its chunks (if any) still exist in the
    table.
    """
    top_k = top_k if top_k is not None else settings.retrieval_top_k
    distance = Chunk.embedding.cosine_distance(query_embedding)

    stmt = (
        select(Chunk, distance.label("distance"))
        .join(Document, Chunk.document_id == Document.id)
        .where(Document.status == "active")
    )
    if equipment_id is not None:
        stmt = stmt.where(Document.equipment_id == equipment_id)
    if plant_id is not None:
        stmt = stmt.where(Document.plant_id == plant_id)
    stmt = stmt.order_by(distance).limit(top_k)

    rows = db.execute(stmt).all()
    return [RetrievedChunk(chunk=chunk, similarity=1 - distance) for chunk, distance in rows]

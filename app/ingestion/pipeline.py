"""Ingestion pipeline.

Ties extraction, cleaning, chunking, embedding, and persistence together
into one function so it can be called identically from a fresh upload and
from a re-index — there's exactly one ingestion code path, not two that
could drift.
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from app.data.models.chunk import Chunk
from app.data.models.document import Document
from app.data.repositories.chunk_repository import ChunkRepository
from app.ingestion.chunking import chunk_pages
from app.ingestion.cleaning import clean_text
from app.ingestion.extractors import ExtractedPage, extract_pages
from app.rag.embedding_client import EmbeddingClient


def run_ingestion(
    db: Session,
    document: Document,
    file_bytes: bytes,
    filename: str,
    embedding_client: EmbeddingClient,
) -> int:
    """Runs the full ingestion pipeline for one document.

    Replaces any existing chunks for this document (supports re-index) and
    returns the number of chunks written. Does not commit — the caller
    (app/services/document_service.py::run_ingestion_job) controls the
    transaction boundary alongside the document's status update.
    """
    pages = extract_pages(file_bytes, filename)
    cleaned_pages = [ExtractedPage(p.page_number, clean_text(p.text)) for p in pages]
    candidates = chunk_pages(cleaned_pages)

    chunk_repo = ChunkRepository(db)
    chunk_repo.delete_by_document(document.id)

    if not candidates:
        return 0

    embeddings = embedding_client.embed([c.text for c in candidates])

    chunks = [
        Chunk(
            id=uuid4(),
            document_id=document.id,
            chunk_index=candidate.chunk_index,
            text=candidate.text,
            token_count=candidate.token_count,
            embedding=embedding,
            chunk_metadata={
                "page_number": candidate.page_number,
                "section_title": candidate.section_title,
                "equipment_id": document.equipment_id,
                "plant_id": document.plant_id,
            },
        )
        for candidate, embedding in zip(candidates, embeddings, strict=True)
    ]
    chunk_repo.create_many(chunks)
    return len(chunks)

"""Chunk model.

Embeddings live in the same table as the chunk's text and metadata — one
Postgres store for relational data and vectors (pgvector), not a separate
vector database service. See EDD §11/§15/§20.

The `metadata` DB column holds page/section/equipment/plant context as
JSONB (see app/ingestion/chunking.py and app/ingestion/pipeline.py for what
gets written). The Python attribute is named `chunk_metadata`, not
`metadata` — SQLAlchemy's declarative `Base` reserves the `metadata` name
for the table-metadata registry, so a same-named column attribute would
collide with it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.data.base import Base

# text-embedding-3-small (the default provider/model, see
# app/rag/embedding_client.py) produces 1536-dimensional vectors. Changing
# embedding provider/model to a different dimensionality requires a new
# migration to alter this column — an accepted, documented limitation of
# using a fixed-width pgvector column rather than a schemaless store.
EMBEDDING_DIMENSION = 1536


class Chunk(Base):
    __tablename__ = "chunk"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("document.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSION), nullable=False)
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

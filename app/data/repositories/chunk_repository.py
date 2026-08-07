"""Chunk repository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select

from app.data.models.chunk import Chunk
from app.data.repositories.base import BaseRepository


class ChunkRepository(BaseRepository[Chunk]):
    model = Chunk

    def create_many(self, chunks: list[Chunk]) -> None:
        self.db.add_all(chunks)

    def delete_by_document(self, document_id: UUID) -> None:
        """Removes a document's existing chunks — supports re-index (a
        re-upload or POST /documents/{id}/reindex replaces chunks in
        place rather than accumulating stale ones alongside new ones).
        """
        self.db.execute(delete(Chunk).where(Chunk.document_id == document_id))

    def count_by_document(self, document_id: UUID) -> int:
        stmt = select(Chunk).where(Chunk.document_id == document_id)
        return len(list(self.db.execute(stmt).scalars().all()))

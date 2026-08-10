"""Citation repository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.data.models.citation import Citation
from app.data.repositories.base import BaseRepository


class CitationRepository(BaseRepository[Citation]):
    model = Citation

    def create_many(self, citations: list[Citation]) -> None:
        self.db.add_all(citations)

    def list_by_message(self, message_id: UUID) -> list[Citation]:
        stmt = select(Citation).where(Citation.message_id == message_id)
        return list(self.db.execute(stmt).scalars().all())

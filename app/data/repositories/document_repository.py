"""Document repository.

No commits happen here — transaction boundaries belong to the service
layer (app/services/document_service.py), not the repository, so a
service method that touches multiple repositories can still control
exactly when its work becomes durable.
"""

from __future__ import annotations

from sqlalchemy import select

from app.data.models.document import Document
from app.data.repositories.base import BaseRepository


class DocumentRepository(BaseRepository[Document]):
    model = Document

    def create(self, document: Document) -> Document:
        return self.add(document)

    def list(
        self,
        *,
        equipment_id: str | None = None,
        plant_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Document]:
        stmt = select(Document)
        if equipment_id is not None:
            stmt = stmt.where(Document.equipment_id == equipment_id)
        if plant_id is not None:
            stmt = stmt.where(Document.plant_id == plant_id)
        if status is not None:
            stmt = stmt.where(Document.status == status)
        stmt = stmt.order_by(Document.created_at.desc()).limit(limit).offset(offset)
        return list(self.db.execute(stmt).scalars().all())

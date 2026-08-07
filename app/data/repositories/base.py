"""Generic base repository.

Holds only what's genuinely common across every repository (get-by-id,
add-to-session). Anything entity-specific (filtered listing, bulk delete,
status transitions) belongs on the concrete repository subclass, not
forced up into this base — see document_repository.py and
chunk_repository.py for how little they actually share.
"""

from __future__ import annotations

from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy.orm import Session

from app.data.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, id_: UUID) -> ModelT | None:
        return self.db.get(self.model, id_)

    def add(self, obj: ModelT) -> ModelT:
        self.db.add(obj)
        return obj

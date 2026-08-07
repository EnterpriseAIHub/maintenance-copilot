"""SQLAlchemy declarative base.

Kept as its own module (rather than defined inline in session.py or a
model file) so alembic/env.py and every model module import the same
Base without a circular import — this is the one file every ORM model in
app/data/models/ (added starting Phase 2) will import.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models owned by this repo.

    Per NFR6, this repo only ever defines models for tables it owns
    (document, chunk, conversation, message, citation, feedback,
    escalation — see EDD §11). Equipment and WorkOrder are never modeled
    here; they're read via API and represented as plain Pydantic schemas
    in app/schemas/platform_contracts.py, not ORM models.
    """

"""Integration test fixtures.

Requires a live, migrated Postgres instance at COPILOT_DATABASE_URL (see
tests/integration/test_ready.py's docstring for how to provide one).
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session

from app.data.models.chunk import Chunk
from app.data.models.conversation import Conversation
from app.data.models.document import Document
from app.data.session import SessionLocal


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(autouse=True)
def _clean_tables() -> Generator[None, None, None]:
    """Keeps integration tests independent of each other and of leftover
    data from a previous run, without requiring a full database reset
    between every test.

    Deleting `Conversation` rows is enough to also clear `message` and
    `citation` — both cascade via the real DB-level ON DELETE CASCADE set
    up in migration 0003, not via anything SQLAlchemy does here.
    """
    yield
    with SessionLocal() as session:
        session.query(Conversation).delete()
        session.query(Chunk).delete()
        session.query(Document).delete()
        session.commit()

"""Database engine and session management."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped DB session.

    Every route/service that needs the database takes this as a
    dependency rather than importing SessionLocal directly, so tests can
    override it with a test database session (see tests/integration).
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

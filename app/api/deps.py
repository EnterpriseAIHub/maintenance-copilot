"""Shared FastAPI dependencies.

Routes should depend on the names exported here rather than reaching into
app.data.session or inventing per-route auth logic, so there's exactly one
place to change when a real database session strategy or a real identity
provider is wired in.
"""

from __future__ import annotations

from app.data.session import get_db

__all__ = ["get_db", "get_current_user"]


def get_current_user() -> str:
    """Auth hook — stubbed today, swappable later without changing routes.

    Returns a fixed service-account-style identity for now. This exists so
    that every route/service already depends on "who is calling this,"
    rather than that concept being bolted on later. Once a real
    identity provider exists at the platform level, only this function's
    body changes — no route signatures do.
    """
    return "local-dev-user"

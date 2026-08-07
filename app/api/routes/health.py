"""Liveness and readiness endpoints.

Split into two, matching the EDD's NFR1 (standalone runnability) and the
platform convention established by predictive-maintenance:

- /health: the process is up. No dependencies checked. Used for basic
  liveness probes.
- /ready: the process can actually serve traffic. Checks the one hard
  dependency this repo has at this phase (the database). LLM/embedding
  provider reachability checks are added in Phase 3 once those clients
  exist — not faked here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ready"}

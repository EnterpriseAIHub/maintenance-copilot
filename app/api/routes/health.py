"""Liveness and readiness endpoints.

Split into two, matching the EDD's NFR1 (standalone runnability) and the
platform convention established by predictive-maintenance:

- /health: the process is up. No dependencies checked. Used for basic
  liveness probes.
- /ready: the process can actually serve traffic. Checks the one hard
  dependency this repo has (the database). Deliberately does NOT also
  call out to the LLM/embedding provider on every readiness probe, even
  though those clients now exist as of Phase 3: readiness probes run
  frequently, and turning each one into a paid external API call is a
  cost/rate-limit risk for no real benefit — provider failures already
  surface per-request as a normal error response from POST /query. See
  PROJECT_PROGRESS.md's Phase 3 decision log.
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

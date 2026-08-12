"""Escalation endpoints (Phase 5) — the review queue.

Top-level, not nested under /conversations — a reviewer works this queue
across conversations, not within one. Deliberately minimal: list by
status, fetch one, resolve one. No assignment/routing across reviewers —
see app/data/models/escalation.py's docstring and
PROJECT_PROGRESS.md's platform-wide deferred table ("one reviewer, one
queue" is the stated scope for this phase).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.data.models.escalation import ESCALATION_STATUSES
from app.schemas.escalation import EscalationRead, EscalationResolveRequest
from app.services.errors import ValidationError
from app.services.escalation_service import EscalationService

router = APIRouter(prefix="/escalations", tags=["escalations"])


@router.get("", response_model=list[EscalationRead])
def list_escalations(
    status_filter: str = Query("open", alias="status"),
    db: Session = Depends(get_db),
) -> list[EscalationRead]:
    if status_filter not in ESCALATION_STATUSES:
        raise ValidationError(
            f"Invalid status filter: '{status_filter}'. Must be one of {ESCALATION_STATUSES}",
            detail={"status": status_filter},
        )
    service = EscalationService(db)
    escalations = service.list_escalations(status=status_filter)
    return [EscalationRead.model_validate(e) for e in escalations]


@router.get("/{escalation_id}", response_model=EscalationRead)
def get_escalation(escalation_id: UUID, db: Session = Depends(get_db)) -> EscalationRead:
    service = EscalationService(db)
    escalation = service.get_escalation(escalation_id)
    return EscalationRead.model_validate(escalation)


@router.post("/{escalation_id}/resolve", response_model=EscalationRead)
def resolve_escalation(
    escalation_id: UUID,
    request: EscalationResolveRequest,
    db: Session = Depends(get_db),
) -> EscalationRead:
    service = EscalationService(db)
    escalation = service.resolve(escalation_id, resolution_note=request.resolution_note)
    return EscalationRead.model_validate(escalation)

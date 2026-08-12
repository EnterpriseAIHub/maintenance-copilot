"""Escalation service.

`escalate_if_needed()` is the one place both trigger paths funnel
through — app/services/conversation_service.py calls it right after
persisting an assistant message (auto-trigger: confidence below
COPILOT_CONFIDENCE_THRESHOLD), and app/services/feedback_service.py calls
it when a technician submits `helpful=False` feedback. Funneling both
through one function is specifically so the "don't create a second open
escalation for a message that already has one" dedup check lives in
exactly one place, not duplicated across both call sites.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.data.models.escalation import Escalation
from app.data.models.message import Message
from app.data.repositories.escalation_repository import EscalationRepository
from app.services.errors import NotFoundError


class EscalationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.escalations = EscalationRepository(db)

    def escalate_if_needed(self, message: Message, *, reason: str) -> Escalation | None:
        """Creates an Escalation for `message` unless one is already open
        for it. Returns the (new or pre-existing open) Escalation, or
        None if `message` isn't an assistant message — a user's own
        question is never itself something to escalate.
        """
        if message.role != "assistant":
            return None

        existing = self.escalations.get_open_for_message(message.id)
        if existing is not None:
            return existing

        escalation = Escalation(
            id=uuid4(),
            message_id=message.id,
            conversation_id=message.conversation_id,
            reason=reason,
            status="open",
            confidence=message.confidence if message.confidence is not None else 0.0,
            answer_snapshot=message.content,
        )
        self.escalations.create(escalation)
        return escalation

    def get_escalation(self, escalation_id: UUID) -> Escalation:
        escalation = self.escalations.get(escalation_id)
        if escalation is None:
            raise NotFoundError(
                f"Escalation {escalation_id} not found",
                detail={"escalation_id": str(escalation_id)},
            )
        return escalation

    def list_escalations(self, *, status: str) -> list[Escalation]:
        return self.escalations.list_by_status(status)

    def resolve(self, escalation_id: UUID, *, resolution_note: str | None) -> Escalation:
        """The complete unit of work for POST /escalations/{id}/resolve —
        commits internally, unlike escalate_if_needed() above (which is
        always a sub-step of some other service's own transaction, not a
        top-level operation on its own — see module docstring)."""
        escalation = self.get_escalation(escalation_id)
        escalation.status = "resolved"
        escalation.resolution_note = resolution_note
        escalation.resolved_at = datetime.now(UTC)
        self.db.commit()
        return escalation

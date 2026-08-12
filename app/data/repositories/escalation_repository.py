"""Escalation repository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.data.models.escalation import Escalation
from app.data.repositories.base import BaseRepository


class EscalationRepository(BaseRepository[Escalation]):
    model = Escalation

    def create(self, escalation: Escalation) -> Escalation:
        return self.add(escalation)

    def get_open_for_message(self, message_id: UUID) -> Escalation | None:
        """Used by app/services/escalation_service.py to avoid creating a
        second open escalation for a message that already has one (the
        low-confidence auto-trigger and the negative-feedback trigger can
        both fire for the same message).
        """
        stmt = select(Escalation).where(
            Escalation.message_id == message_id, Escalation.status == "open"
        )
        return self.db.execute(stmt).scalars().first()

    def list_by_status(self, status: str) -> list[Escalation]:
        stmt = (
            select(Escalation)
            .where(Escalation.status == status)
            .order_by(Escalation.created_at.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

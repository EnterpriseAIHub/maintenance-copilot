"""Feedback service.

Owns feedback submission the way DocumentService/ConversationService own
their own resources. `submit_feedback()` is the complete unit of work for
POST /conversations/{cid}/messages/{mid}/feedback — commits once, after
both the feedback row and (if triggered) the escalation are staged, so
the two writes land together.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.data.models.feedback import Feedback
from app.data.models.message import Message
from app.data.repositories.feedback_repository import FeedbackRepository
from app.data.repositories.message_repository import MessageRepository
from app.services.errors import NotFoundError
from app.services.escalation_service import EscalationService


class FeedbackService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.feedback = FeedbackRepository(db)
        self.messages = MessageRepository(db)
        self.escalations = EscalationService(db)

    def submit_feedback(
        self,
        conversation_id: UUID,
        message_id: UUID,
        *,
        helpful: bool,
        comment: str | None,
        submitted_by: str,
    ) -> Feedback:
        message = self._get_message_in_conversation(conversation_id, message_id)

        feedback = Feedback(
            id=uuid4(),
            message_id=message.id,
            helpful=helpful,
            comment=comment,
            submitted_by=submitted_by,
        )
        self.feedback.create(feedback)

        if not helpful:
            self.escalations.escalate_if_needed(message, reason="negative_feedback")

        self.db.commit()
        return feedback

    def _get_message_in_conversation(self, conversation_id: UUID, message_id: UUID) -> Message:
        message = self.messages.get(message_id)
        if message is None or message.conversation_id != conversation_id:
            # Deliberately the same error/detail shape whether the message
            # doesn't exist at all or exists but belongs to a different
            # conversation — a client that guesses/reuses a message_id
            # across conversations shouldn't learn which case it hit.
            raise NotFoundError(
                f"Message {message_id} not found in conversation {conversation_id}",
                detail={"conversation_id": str(conversation_id), "message_id": str(message_id)},
            )
        return message

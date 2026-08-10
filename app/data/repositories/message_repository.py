"""Message repository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.data.models.message import Message
from app.data.repositories.base import BaseRepository


class MessageRepository(BaseRepository[Message]):
    model = Message

    def create(self, message: Message) -> Message:
        return self.add(message)

    def list_by_conversation(self, conversation_id: UUID) -> list[Message]:
        """Full history, oldest first — the order a conversation reads in."""
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_recent_by_conversation(self, conversation_id: UUID, limit: int) -> list[Message]:
        """The most recent `limit` messages, oldest-first once returned —
        used to build bounded conversation_history for the LLM prompt
        (see app/services/conversation_service.py), not for the full
        GET /conversations/{id}/messages history view.
        """
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        return list(reversed(list(self.db.execute(stmt).scalars().all())))

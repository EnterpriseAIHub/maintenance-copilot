"""Conversation repository.

No commits here — same rule as document_repository.py: transaction
boundaries belong to the service layer.
"""

from __future__ import annotations

from app.data.models.conversation import Conversation
from app.data.repositories.base import BaseRepository


class ConversationRepository(BaseRepository[Conversation]):
    model = Conversation

    def create(self, conversation: Conversation) -> Conversation:
        return self.add(conversation)

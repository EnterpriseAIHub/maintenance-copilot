"""Feedback repository."""

from __future__ import annotations

from app.data.models.feedback import Feedback
from app.data.repositories.base import BaseRepository


class FeedbackRepository(BaseRepository[Feedback]):
    model = Feedback

    def create(self, feedback: Feedback) -> Feedback:
        return self.add(feedback)

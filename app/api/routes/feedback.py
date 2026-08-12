"""Feedback endpoint (Phase 5).

Nested under /conversations/{conversation_id}/messages/{message_id} —
unlike escalations (a cross-cutting review queue, see
app/api/routes/escalations.py), feedback is always about one specific
message in one specific conversation, so it follows the same resource
hierarchy already established for messages themselves. Verifying the
message actually belongs to the given conversation (not just that it
exists) happens in app/services/feedback_service.py.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.schemas.feedback import FeedbackCreateRequest, FeedbackRead
from app.services.feedback_service import FeedbackService

router = APIRouter(prefix="/conversations", tags=["feedback"])


@router.post(
    "/{conversation_id}/messages/{message_id}/feedback",
    response_model=FeedbackRead,
    status_code=status.HTTP_201_CREATED,
)
def submit_feedback(
    conversation_id: UUID,
    message_id: UUID,
    request: FeedbackCreateRequest,
    db: Session = Depends(get_db),
    submitted_by: str = Depends(get_current_user),
) -> FeedbackRead:
    service = FeedbackService(db)
    feedback = service.submit_feedback(
        conversation_id,
        message_id,
        helpful=request.helpful,
        comment=request.comment,
        submitted_by=submitted_by,
    )
    return FeedbackRead.model_validate(feedback)

"""Conversation endpoints.

POST /conversations/{id}/messages streams Server-Sent Events rather than
returning a single JSON response: `retrieving` -> `generating` -> `done`
(or `error`). Per-phase decision (see PROJECT_PROGRESS.md's Phase 4
notes): real token-by-token streaming isn't implemented, because Phase
3's citation strategy forces a tool call (`provide_answer`) whose answer
text is a field inside a JSON object, not free-flowing text — streaming
that cleanly would mean incrementally parsing partial JSON, which is
real added complexity for a stage-progress signal that conveys most of
the same value more simply.

Like documents.py, this route is a plain `def`, not `async def` — the
work underneath (DB calls, the LLM call) is all blocking. The streaming
generator returned to StreamingResponse is a plain sync generator too;
Starlette wraps sync generators with `iterate_in_threadpool` internally,
so each step still runs off the event loop without introducing any new
async pattern into a codebase that doesn't otherwise use one.

Conversation-not-found and empty-question validation happen before the
StreamingResponse is constructed, so those failures still go through the
normal AppError JSON envelope (headers/status line not yet committed at
that point) — only failures *during* the RAG pipeline itself become an
`error` SSE event, since by then a 200 response has already started.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.schemas.conversation import (
    ConversationCreateRequest,
    ConversationRead,
    MessageCreateRequest,
    MessageRead,
)
from app.services.conversation_service import ConversationService
from app.services.errors import ValidationError

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
def create_conversation(
    request: ConversationCreateRequest,
    db: Session = Depends(get_db),
    started_by: str = Depends(get_current_user),
) -> ConversationRead:
    service = ConversationService(db)
    conversation = service.create_conversation(
        equipment_id=request.equipment_id,
        plant_id=request.plant_id,
        started_by=started_by,
    )
    return ConversationRead.model_validate(conversation)


@router.get("/{conversation_id}", response_model=ConversationRead)
def get_conversation(conversation_id: UUID, db: Session = Depends(get_db)) -> ConversationRead:
    service = ConversationService(db)
    conversation = service.get_conversation(conversation_id)
    return ConversationRead.model_validate(conversation)


@router.get("/{conversation_id}/messages", response_model=list[MessageRead])
def list_messages(conversation_id: UUID, db: Session = Depends(get_db)) -> list[MessageRead]:
    service = ConversationService(db)
    service.get_conversation(conversation_id)  # 404 if the conversation doesn't exist
    return service.list_messages(conversation_id)


@router.post("/{conversation_id}/messages", response_model=None)
def post_message(
    conversation_id: UUID,
    request: MessageCreateRequest,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    if not request.question.strip():
        raise ValidationError("question must not be empty", detail={"question": request.question})

    service = ConversationService(db)
    conversation = service.get_conversation(conversation_id)  # 404 before streaming starts

    def event_stream() -> Generator[str, None, None]:
        for event in service.generate_answer_stream(conversation, request.question):
            yield f"event: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

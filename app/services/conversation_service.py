"""Conversation service.

Owns conversation/message/citation state transitions the same way
DocumentService owns document ingestion state — routes stay thin, this
layer controls its own transaction boundaries (repositories never
commit; see app/data/repositories/base.py).

`generate_answer_stream()` is a generator, not a single return, because
app/api/routes/conversations.py needs to emit SSE progress events
(retrieving/generating/done) around the actual work. It's still a plain
synchronous generator — no new async pattern introduced, see
conversations.py's module docstring for why that's fine under Starlette's
StreamingResponse.
"""

from __future__ import annotations

from collections.abc import Generator
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.config.settings import settings
from app.data.models.citation import Citation as CitationModel
from app.data.models.conversation import Conversation
from app.data.models.message import Message
from app.data.repositories.citation_repository import CitationRepository
from app.data.repositories.conversation_repository import ConversationRepository
from app.data.repositories.message_repository import MessageRepository
from app.rag.orchestrator import RagAnswer, answer_question
from app.rag.prompt_builder import ConversationTurn
from app.schemas.conversation import CitationRead, MessageRead
from app.services.errors import NotFoundError


class ConversationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.conversations = ConversationRepository(db)
        self.messages = MessageRepository(db)
        self.citations = CitationRepository(db)

    def create_conversation(
        self, *, equipment_id: str | None, plant_id: str | None, started_by: str
    ) -> Conversation:
        conversation = Conversation(
            id=uuid4(),
            equipment_id=equipment_id,
            plant_id=plant_id,
            started_by=started_by,
        )
        self.conversations.create(conversation)
        self.db.commit()
        return conversation

    def get_conversation(self, conversation_id: UUID) -> Conversation:
        conversation = self.conversations.get(conversation_id)
        if conversation is None:
            raise NotFoundError(
                f"Conversation {conversation_id} not found",
                detail={"conversation_id": str(conversation_id)},
            )
        return conversation

    def list_messages(self, conversation_id: UUID) -> list[MessageRead]:
        """Full history for GET /conversations/{id}/messages, oldest first."""
        messages = self.messages.list_by_conversation(conversation_id)
        return [self._to_message_read(m) for m in messages]

    def generate_answer_stream(
        self, conversation: Conversation, question: str
    ) -> Generator[dict, None, None]:
        """Persists the user turn, runs the RAG pipeline, persists the
        assistant turn + citations, and yields SSE-ready event dicts
        along the way: {"event": "retrieving"|"generating"|"done"|"error",
        "data": {...}}.

        Each DB write below commits on its own rather than as one
        transaction spanning the whole generator — matching the same
        per-step-commits approach already used by
        app/ingestion/pipeline.py::run_ingestion (see
        PROJECT_PROGRESS.md's "Known limitations": acceptable at this
        scale, not hardened into a single atomic transaction). The
        practical reason here is stronger, not just consistent: a
        StreamingResponse's client can disconnect mid-stream, and the
        user's own message should still be saved even if that happens or
        if the LLM call itself fails afterward.
        """
        user_message = Message(
            id=uuid4(),
            conversation_id=conversation.id,
            role="user",
            content=question,
        )
        self.messages.create(user_message)
        self.db.commit()

        yield {"event": "retrieving", "data": {}}

        history = self._load_conversation_history(conversation.id)

        yield {"event": "generating", "data": {}}

        try:
            result = answer_question(
                self.db,
                question,
                equipment_id=conversation.equipment_id,
                plant_id=conversation.plant_id,
                conversation_history=history,
            )
        except Exception as exc:  # noqa: BLE001 — deliberately broad: this is
            # the last point before the SSE stream ends, and any failure here
            # (LLM provider error, embedding provider error, etc.) needs to
            # reach the client as a clean "error" event rather than crash the
            # generator mid-stream with a raw traceback.
            yield {
                "event": "error",
                "data": {"code": "RAG_PIPELINE_ERROR", "message": str(exc)},
            }
            return

        assistant_message = self._persist_assistant_turn(conversation.id, result)
        self.db.commit()

        message_read = self._to_message_read(assistant_message, citations=result.citations)
        yield {"event": "done", "data": message_read.model_dump(mode="json")}

    def _persist_assistant_turn(self, conversation_id: UUID, result: RagAnswer) -> Message:
        assistant_message = Message(
            id=uuid4(),
            conversation_id=conversation_id,
            role="assistant",
            content=result.answer,
            confidence=result.confidence,
            retrieved_chunk_count=result.retrieved_chunk_count,
        )
        self.messages.create(assistant_message)
        self.db.flush()  # assistant_message.id must exist before citations reference it

        citation_rows = [
            CitationModel(
                id=uuid4(),
                message_id=assistant_message.id,
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                section_title=c.section_title,
                page_number=c.page_number,
                snippet=c.snippet,
            )
            for c in result.citations
        ]
        if citation_rows:
            self.citations.create_many(citation_rows)

        return assistant_message

    def _load_conversation_history(self, conversation_id: UUID) -> list[ConversationTurn]:
        """Pairs up the most recent user/assistant messages (bounded by
        COPILOT_CONVERSATION_HISTORY_LIMIT turns) into ConversationTurn
        objects for the LLM prompt. The just-created user message (for the
        question currently being answered) is intentionally excluded —
        history is *prior* turns, the current question is passed to
        answer_question() separately.
        """
        limit = settings.conversation_history_limit
        if limit <= 0:
            return []

        # Over-fetched by one extra pair: the user message for the
        # question currently being answered was already committed above
        # (before this method runs), so it's the most recent row fetched
        # here. It has no matching assistant reply yet, so the pairing
        # loop below naturally drops it as a dangling, unpaired question
        # rather than treating it as history — but without fetching one
        # extra pair up front, that dangling row would silently consume
        # one of the `limit` history slots instead of just being ignored.
        recent = self.messages.list_recent_by_conversation(conversation_id, (limit + 1) * 2)

        turns: list[ConversationTurn] = []
        pending_question: str | None = None
        for message in recent:
            if message.role == "user":
                pending_question = message.content
            elif message.role == "assistant" and pending_question is not None:
                turns.append(ConversationTurn(question=pending_question, answer=message.content))
                pending_question = None

        return turns[-limit:]

    def _to_message_read(self, message: Message, citations: list | None = None) -> MessageRead:
        if citations is None:
            citation_rows = self.citations.list_by_message(message.id)
            citation_reads = [CitationRead.model_validate(c) for c in citation_rows]
        else:
            citation_reads = [
                CitationRead(
                    chunk_id=c.chunk_id,
                    document_id=c.document_id,
                    section_title=c.section_title,
                    page_number=c.page_number,
                    snippet=c.snippet,
                )
                for c in citations
            ]

        return MessageRead(
            id=message.id,
            conversation_id=message.conversation_id,
            role=message.role,
            content=message.content,
            confidence=message.confidence,
            retrieved_chunk_count=message.retrieved_chunk_count,
            citations=citation_reads,
            created_at=message.created_at,
        )

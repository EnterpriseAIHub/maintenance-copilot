"""Agent service (Phase 6).

`answer_for_agent()` calls `app/rag/orchestrator.py::answer_question()`
completely unchanged — identical to how `/query` (Phase 3) and
`/conversations` (Phase 4) already call it — and builds an `AgentResponse`
(EDD §12) directly from the result. Nothing else happens here.

No predictive-maintenance enrichment call in this module. That call lives
in `app/services/conversation_service.py` instead — EDD §10 documents
`context_from_predictive_maintenance` as part of the
`/conversations/{id}/messages` response shape, not `/agent`'s (`/agent`'s
response shape is fixed by EDD §12's `AgentResponse`, which has no such
field). Keeping `/agent` free of any cross-repo call also keeps the one
orchestrator-facing contract in this repo byte-identical to what a real
`platform-orchestrator` would expect from *any* repo speaking this same
Agent Contract — adding a repo-specific extra field there would have
broken that "same shape" guarantee (EDD §1.2).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.rag.citation_extractor import Citation
from app.rag.orchestrator import answer_question
from app.schemas.platform_contracts import AgentResponse


def answer_for_agent(
    db: Session,
    query: str,
    *,
    equipment_id: str | None = None,
    plant_id: str | None = None,
) -> AgentResponse:
    result = answer_question(db, query, equipment_id=equipment_id, plant_id=plant_id)

    return AgentResponse(
        answer=result.answer,
        confidence=result.confidence,
        provenance=[_format_provenance(c) for c in result.citations],
        structured_data=None,
    )


def _format_provenance(citation: Citation) -> str:
    """EDD §12 specifies `provenance: list[str]` without further format —
    this repo picks a compact, human-readable string carrying the same
    identifying fields `/query`/`/conversations` expose as structured
    citation objects, since a `str` alone shouldn't lose that information.
    """
    location = f"document={citation.document_id} chunk={citation.chunk_id}"
    if citation.page_number is not None:
        location += f" page={citation.page_number}"
    if citation.section_title:
        location += f" section={citation.section_title!r}"
    return location

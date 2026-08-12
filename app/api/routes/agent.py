"""Agent endpoint (Phase 6).

This is a *provider* of data to a future orchestrator (Project 3,
`platform-orchestrator`), not a consumer/composer of other repos' data —
see PROJECT_PROGRESS.md's architectural review notes. It must not grow
into a second orchestration surface: no combining/reasoning across
multiple other repos' outputs here, ever, and (per EDD §12) no
predictive-maintenance enrichment either — that lives on
`/conversations/{id}/messages` instead (see app/services/
conversation_service.py), since `AgentResponse`'s shape is fixed by the
Agent Contract and has no field for it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.platform_contracts import AgentRequest, AgentResponse
from app.services.agent_service import answer_for_agent
from app.services.errors import ValidationError

router = APIRouter(tags=["agent"])


@router.post("/agent", response_model=AgentResponse)
def agent(request: AgentRequest, db: Session = Depends(get_db)) -> AgentResponse:
    if not request.query.strip():
        raise ValidationError("query must not be empty", detail={"query": request.query})

    return answer_for_agent(
        db,
        request.query,
        equipment_id=request.context.get("equipment_id"),
        plant_id=request.context.get("plant_id"),
    )

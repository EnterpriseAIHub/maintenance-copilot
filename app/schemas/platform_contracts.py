"""Vendored platform contract types (Phase 6).

Per EDD §12, this repo vendors (hand-copies) the request/response shapes
`predictive-maintenance` exposes on its own `/agent` surface, rather than
depending on a shared package — see PROJECT_PROGRESS.md's Phase 1
decision log for why (two repos, one developer; packaging overhead
exceeds benefit at this scale; revisit if a third project ever consumes
the same contract). The documented trade-off that justifies vendoring
instead of a shared package is that these types are kept in sync with
the real ones *by hand* — drift is a real, standing risk of this
approach, not a hypothetical one.

This file's shapes match EDD §12 exactly, with two corrections confirmed
directly against predictive-maintenance's actual running schema (not
inferred, and not taken from an earlier review document that turned out
to conflict with this repo's own EDD text on these same two fields — see
PROJECT_PROGRESS.md's "Architectural review corrections" section for the
full reconciliation):

- `structured_data: dict[str, Any] | None = None` — this has been the
  real schema since Project 1's Phase 0. The EDD's literal `= {}` text
  was wrong from the start, not something that drifted later.
- `confidence: float = Field(ge=0.0, le=1.0)` — added in Project 1's
  Phase 11, after a bug where an unconstrained value produced a
  nonsensical confidence (e.g. `5.0`) with no validation error. The
  EDD's literal unbounded `confidence: float` text predates that fix.

Every other field below — `AgentRequest.query`/`context`,
`AgentResponse.provenance`, and both `EquipmentRef`/`WorkOrderRef` — is
confirmed correct exactly as EDD §12 specifies, including
`AgentRequest.context` being a loose `dict[str, Any]` rather than a
structured type: this repo does not get to unilaterally make the
platform-facing contract stricter than the platform actually defines it,
even when a structured type would be more convenient here.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EquipmentRef(BaseModel):
    equipment_id: str
    plant_id: str | None = None
    display_name: str | None = None


class WorkOrderRef(BaseModel):
    work_order_id: str
    equipment_id: str
    status: str
    priority: str


class AgentRequest(BaseModel):
    query: str
    context: dict[str, Any] = {}


class AgentResponse(BaseModel):
    answer: str
    # Corrected per Project 1's Phase 11 fix — see module docstring.
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: list[str]
    # Corrected — this has been the real default since Project 1's Phase
    # 0, not `{}`. See module docstring.
    structured_data: dict[str, Any] | None = None


__all__ = ["EquipmentRef", "WorkOrderRef", "AgentRequest", "AgentResponse"]

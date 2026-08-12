"""Contract check (EDD §17): asserts this repo's vendored
app/schemas/platform_contracts.py shapes match EDD §12 exactly, including
the two fields confirmed correct against predictive-maintenance's actual
running schema rather than the EDD's literal (stale, on these two fields
only) text — see that module's docstring, and PROJECT_PROGRESS.md's
"Architectural review corrections" section for the full reconciliation.
This test exists so a future hand-sync edit that reintroduces drift on
any of these fields fails loudly here rather than being caught only by a
future cross-repo review.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.schemas.platform_contracts import AgentRequest, AgentResponse, EquipmentRef, WorkOrderRef


def _valid_response_kwargs(**overrides: object) -> dict:
    base = {"answer": "some answer", "confidence": 0.8, "provenance": []}
    base.update(overrides)
    return base


def test_agent_request_uses_query_and_context_fields() -> None:
    # EDD §12: AgentRequest.query (not "question"), context: dict (not a
    # structured type) — a prior implementation got both wrong.
    request = AgentRequest(query="How often should P-101 be lubricated?")

    assert request.query == "How often should P-101 be lubricated?"
    assert request.context == {}


def test_agent_request_context_accepts_arbitrary_keys() -> None:
    request = AgentRequest(query="q", context={"equipment_id": "EQ-1", "plant_id": "P-1"})

    assert request.context == {"equipment_id": "EQ-1", "plant_id": "P-1"}


def test_agent_response_uses_provenance_not_citations() -> None:
    response = AgentResponse(**_valid_response_kwargs(provenance=["document=... chunk=..."]))

    assert response.provenance == ["document=... chunk=..."]
    assert not hasattr(response, "citations")


def test_confidence_accepts_values_within_bounds() -> None:
    AgentResponse(**_valid_response_kwargs(confidence=0.0))
    AgentResponse(**_valid_response_kwargs(confidence=1.0))
    AgentResponse(**_valid_response_kwargs(confidence=0.5))


def test_confidence_rejects_values_above_one() -> None:
    with pytest.raises(PydanticValidationError):
        AgentResponse(**_valid_response_kwargs(confidence=5.0))


def test_confidence_rejects_negative_values() -> None:
    with pytest.raises(PydanticValidationError):
        AgentResponse(**_valid_response_kwargs(confidence=-0.1))


def test_structured_data_defaults_to_none_not_empty_dict() -> None:
    response = AgentResponse(**_valid_response_kwargs())

    assert response.structured_data is None
    # Specifically not {} — see platform_contracts.py's module docstring
    # on why these are different values over the wire.
    assert response.structured_data != {}


def test_agent_response_has_no_predictive_maintenance_field() -> None:
    # EDD §12's AgentResponse has no context_from_predictive_maintenance
    # field — that enrichment belongs on /conversations/{id}/messages
    # (EDD §10) instead. A prior implementation incorrectly added it here.
    response = AgentResponse(**_valid_response_kwargs())

    assert not hasattr(response, "context_from_predictive_maintenance")


def test_equipment_ref_has_all_edd_fields() -> None:
    ref = EquipmentRef(equipment_id="EQ-1", plant_id="PLANT-A", display_name="Pump P-101")

    assert ref.equipment_id == "EQ-1"
    assert ref.plant_id == "PLANT-A"
    assert ref.display_name == "Pump P-101"


def test_work_order_ref_has_all_edd_fields() -> None:
    ref = WorkOrderRef(work_order_id="WO-1", equipment_id="EQ-1", status="open", priority="high")

    assert ref.work_order_id == "WO-1"
    assert ref.equipment_id == "EQ-1"
    assert ref.status == "open"
    assert ref.priority == "high"

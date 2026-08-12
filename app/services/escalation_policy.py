"""Escalation policy.

Pure, DB-free, model-free decision functions for escalation — deliberately
separate from app/services/escalation_service.py, which owns a different
concern (dedup: "does an open escalation already exist for this
message"). This module owns policy decisions (thresholds, business
rules); escalation_service.py owns state (creating/resolving rows).
Keeping them apart means a policy change is independently testable and
swappable without touching anything that talks to the database.

This mirrors an established pattern from predictive-maintenance
(risk_policy.evaluate_risk()) — a pure function isolating a business
threshold from orchestration code, for the same reason: so it can be
tested directly and changed without touching call sites that trigger it.
"""

from __future__ import annotations

from app.config.settings import settings


def should_escalate_for_confidence(confidence: float, threshold: float | None = None) -> bool:
    """True when `confidence` falls below the escalation threshold.

    `threshold` defaults to COPILOT_CONFIDENCE_THRESHOLD when not passed
    explicitly. Confidence exactly at the threshold does NOT escalate —
    the threshold is the minimum acceptable confidence, not the maximum
    escalatable one.
    """
    if threshold is None:
        threshold = settings.confidence_threshold
    return confidence < threshold

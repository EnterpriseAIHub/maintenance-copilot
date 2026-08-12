"""Predictive-maintenance enrichment client (Phase 6).

The one, narrowly-scoped synchronous call this repo makes to another
domain repo: `GET /equipment/{id}/risk` on a running `predictive-maintenance`
instance, fetching one piece of supplementary read-only context for an
already-fully-computed RAG answer. This is enrichment, not composition —
it never affects retrieval, the LLM prompt, citations, or confidence; it's
attached to an AgentResponse that would be complete and valid without it.
See PROJECT_PROGRESS.md's architectural-review section for the full
reasoning on why this stays a single narrow call and must never grow into
this repo reasoning across multiple other repos' outputs — that's
Project 3 (`platform-orchestrator`)'s job by design, not this repo's.

Every failure mode degrades to `None`, never an exception: unreachable
host, connection refused, timeout, non-2xx status, malformed response
body. `COPILOT_PREDICTIVE_MAINTENANCE_TIMEOUT_SECONDS` bounds the
worst-case latency this adds to a request — see that setting's docstring
in app/config/settings.py for why the specific value matters (this call
is synchronous within the request, not fire-and-forget). A failed or slow
`predictive-maintenance` must never break, delay past that bound, or
otherwise affect the rest of the answer.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)


def fetch_risk_context(equipment_id: str) -> dict[str, Any] | None:
    """Returns predictive-maintenance's risk context for `equipment_id`,
    or None if unavailable for any reason. Never raises.
    """
    if not settings.predictive_maintenance_base_url:
        # Not configured — this repo must run standalone with zero other
        # repos present (NFR1). Not an error, just nothing to enrich with.
        return None

    url = f"{settings.predictive_maintenance_base_url}/equipment/{equipment_id}/risk"
    try:
        response = httpx.get(url, timeout=settings.predictive_maintenance_timeout_seconds)
        response.raise_for_status()
        data = response.json()
    except Exception:
        # Deliberately broad and deliberately swallowed: any failure here
        # — DNS/connection failure, timeout, non-2xx, invalid JSON — must
        # degrade to "no enrichment" rather than affect the rest of the
        # answer in any way. Logged (not silent) so an operator can still
        # notice a consistently-unreachable predictive-maintenance
        # instance, without it ever surfacing to the caller as an error.
        logger.warning("predictive-maintenance risk enrichment call failed", exc_info=True)
        return None

    if not isinstance(data, dict):
        logger.warning("predictive-maintenance risk enrichment returned a non-object body")
        return None

    return data

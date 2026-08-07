"""Structured JSON logging.

Per NFR5, logs are the audit trail for v1 (see EDD §20) — every request and
service action should be reconstructable after the fact from log output
alone. This module intentionally has no dependency on request-scoped state
yet; per-request correlation IDs are added in Phase 4 when conversations
exist to correlate against, not before.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any


class JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger to emit structured JSON to stdout.

    Called once at application startup (see app/api/main.py). Replaces any
    default handlers rather than adding to them, so log output stays
    consistently JSON regardless of how a hosting platform's runner
    pre-configures logging.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    # Quiet noisy third-party loggers down to warnings by default; this repo's
    # own loggers still respect `level`.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

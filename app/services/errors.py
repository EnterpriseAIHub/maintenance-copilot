"""Shared application exception hierarchy.

Every domain error a service raises should be one of these (or a
subclass), never a bare Exception — app/api/main.py registers a single
FastAPI exception handler that translates any AppError into the standard
error envelope, so routes never need their own try/except-to-HTTP
translation logic.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base class for all domain errors raised by this repo's services."""

    status_code: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class ValidationError(AppError):
    status_code = 422
    code = "VALIDATION_ERROR"


class UnsupportedFileTypeError(AppError):
    """Raised by app/ingestion/extractors.py for an unrecognized file type."""

    status_code = 400
    code = "UNSUPPORTED_FILE_TYPE"

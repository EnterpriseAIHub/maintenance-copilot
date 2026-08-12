"""FastAPI application entrypoint.

All six phases' routers are now registered: health, documents, the
stateless query endpoint, conversations, feedback, escalations, and
agent.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import agent, conversations, documents, escalations, feedback, health, query
from app.config.logging_config import configure_logging
from app.config.settings import settings
from app.services.errors import AppError

configure_logging(settings.log_level)

app = FastAPI(
    title="maintenance-copilot",
    description="RAG-based maintenance knowledge copilot — Enterprise AI Platform, Project A.",
    version="0.1.0",
)

app.include_router(health.router)
app.include_router(documents.router)
app.include_router(query.router)
app.include_router(conversations.router)
app.include_router(feedback.router)
app.include_router(escalations.router)
app.include_router(agent.router)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Translates any AppError into the standard error envelope, so
    individual routes never need their own try/except-to-HTTP logic.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "detail": exc.detail}},
    )

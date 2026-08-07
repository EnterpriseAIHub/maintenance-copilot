"""Unit test for /health.

/health has no dependencies (see app/api/routes/health.py), so it belongs
in unit tests. /ready requires a live database and is covered under
tests/integration instead.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

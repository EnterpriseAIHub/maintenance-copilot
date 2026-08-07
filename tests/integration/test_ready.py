"""Integration test for /ready.

Requires a live Postgres instance reachable at COPILOT_DATABASE_URL with
migrations applied (the CI workflow provisions this via a service
container and `alembic upgrade head` before running tests; locally, run
`docker compose up -d postgres && alembic upgrade head` first).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.main import app

pytestmark = pytest.mark.integration

client = TestClient(app)


def test_ready_returns_ready_when_db_is_reachable() -> None:
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}

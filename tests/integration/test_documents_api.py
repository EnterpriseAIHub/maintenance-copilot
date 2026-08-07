"""End-to-end tests for the document upload/ingestion pipeline against a
real Postgres+pgvector instance, using the fake embedding client
(COPILOT_EMBEDDING_PROVIDER=fake — see .env.example / CI config) so no
external API key or network access is required.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from fpdf import FPDF

from app.api.main import app
from app.data.repositories.chunk_repository import ChunkRepository

pytestmark = pytest.mark.integration

client = TestClient(app)


def _pdf_bytes(text: str = "Bearing replacement procedure: torque to 45 Nm.") -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 10, text)
    return bytes(pdf.output())


def _upload(**overrides: str) -> dict:
    data = {
        "title": "Test Manual",
        "source_type": "manual",
        "equipment_id": "EQ-TEST-1",
        **overrides,
    }
    response = client.post(
        "/documents",
        data=data,
        files={"file": ("test.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 201
    return response.json()


def test_upload_ingests_and_produces_chunks(db_session) -> None:
    created = _upload()

    detail = client.get(f"/documents/{created['document_id']}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "active"

    chunk_count = ChunkRepository(db_session).count_by_document(UUID(created["document_id"]))
    assert chunk_count > 0


def test_upload_unsupported_file_type_returns_error_envelope() -> None:
    response = client.post(
        "/documents",
        data={"title": "Bad File", "source_type": "manual"},
        files={"file": ("notes.txt", b"plain text", "text/plain")},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_get_document_not_found_returns_error_envelope() -> None:
    response = client.get("/documents/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_list_documents_filters_by_equipment_id() -> None:
    _upload(equipment_id="EQ-A")
    _upload(equipment_id="EQ-B")

    response = client.get("/documents", params={"equipment_id": "EQ-A"})

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["equipment_id"] == "EQ-A"


def test_reindex_regenerates_chunks(db_session) -> None:
    created = _upload()
    document_id = UUID(created["document_id"])
    original_count = ChunkRepository(db_session).count_by_document(document_id)

    reindex_response = client.post(f"/documents/{created['document_id']}/reindex")

    assert reindex_response.status_code == 200
    detail = client.get(f"/documents/{created['document_id']}")
    assert detail.json()["status"] == "active"
    db_session.expire_all()
    new_count = ChunkRepository(db_session).count_by_document(document_id)
    assert new_count == original_count  # same source file re-ingested identically
    assert new_count > 0


def test_archive_document_sets_status_archived() -> None:
    created = _upload()

    archive_response = client.delete(f"/documents/{created['document_id']}")
    assert archive_response.status_code == 204

    detail = client.get(f"/documents/{created['document_id']}")
    assert detail.json()["status"] == "archived"

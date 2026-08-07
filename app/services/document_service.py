"""Document service.

Owns document state transitions (processing -> active/failed, archiving)
and file storage. The actual ingestion pipeline call
(app/ingestion/pipeline.py::run_ingestion) is invoked from
`run_ingestion_job`, a module-level function rather than a service method
— see its docstring for why.
"""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.config.settings import settings
from app.data.models.document import Document
from app.data.repositories.document_repository import DocumentRepository
from app.data.session import SessionLocal
from app.ingestion.pipeline import run_ingestion
from app.rag.embedding_client import get_embedding_client
from app.services.errors import NotFoundError

logger = logging.getLogger(__name__)


class DocumentService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.documents = DocumentRepository(db)

    def create_document(
        self,
        *,
        title: str,
        source_type: str,
        equipment_id: str | None,
        plant_id: str | None,
        uploaded_by: str,
        file_bytes: bytes,
        filename: str,
    ) -> Document:
        document_id = uuid4()
        file_path = self._store_file(document_id, filename, file_bytes)

        document = Document(
            id=document_id,
            title=title,
            source_type=source_type,
            equipment_id=equipment_id,
            plant_id=plant_id,
            file_path=str(file_path),
            status="processing",
            uploaded_by=uploaded_by,
        )
        self.documents.create(document)
        self.db.commit()
        self.db.refresh(document)
        return document

    def get_document(self, document_id: UUID) -> Document:
        document = self.documents.get(document_id)
        if document is None:
            raise NotFoundError(
                f"Document {document_id} not found", detail={"document_id": str(document_id)}
            )
        return document

    def list_documents(
        self,
        *,
        equipment_id: str | None = None,
        plant_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Document]:
        return self.documents.list(
            equipment_id=equipment_id, plant_id=plant_id, status=status, limit=limit, offset=offset
        )

    def reindex_document(self, document_id: UUID) -> Document:
        """Marks a document for re-ingestion. The route triggers
        `run_ingestion_job` as a background task after calling this — same
        job function as a fresh upload, so there's one ingestion code path.
        """
        document = self.get_document(document_id)
        document.status = "processing"
        document.error_message = None
        self.db.commit()
        self.db.refresh(document)
        return document

    def archive_document(self, document_id: UUID) -> Document:
        document = self.get_document(document_id)
        document.status = "archived"
        self.db.commit()
        self.db.refresh(document)
        return document

    def mark_active(self, document_id: UUID) -> None:
        document = self.documents.get(document_id)
        if document is not None:
            document.status = "active"
            document.error_message = None
            self.db.commit()

    def mark_failed(self, document_id: UUID, error_message: str) -> None:
        document = self.documents.get(document_id)
        if document is not None:
            document.status = "failed"
            document.error_message = error_message
            self.db.commit()

    @staticmethod
    def _store_file(document_id: UUID, filename: str, file_bytes: bytes) -> Path:
        storage_dir = Path(settings.document_storage_path)
        storage_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(filename).suffix
        file_path = storage_dir / f"{document_id}{suffix}"
        file_path.write_bytes(file_bytes)
        return file_path


def run_ingestion_job(document_id: UUID) -> None:
    """Background ingestion job — runs the pipeline and updates status.

    Opens its own DB session rather than reusing the HTTP request's
    session. This runs as a FastAPI `BackgroundTasks` job, which executes
    after the response has already been sent; giving it an independent
    session makes its lifetime explicit rather than relying on FastAPI's
    dependency-cleanup-after-background-tasks ordering.

    Used identically for a fresh upload and for POST
    /documents/{id}/reindex — one ingestion code path, not two.
    """
    db = SessionLocal()
    try:
        service = DocumentService(db)
        document = service.get_document(document_id)
        try:
            file_bytes = Path(document.file_path).read_bytes()
            embedding_client = get_embedding_client()
            chunk_count = run_ingestion(
                db, document, file_bytes, Path(document.file_path).name, embedding_client
            )
            service.mark_active(document_id)
            logger.info(
                "Ingestion succeeded",
                extra={"document_id": str(document_id), "chunk_count": chunk_count},
            )
        # A broad catch here is intentional: the worker must record failure
        # and return cleanly, never crash the process mid-ingestion.
        except Exception as exc:
            logger.exception("Ingestion failed", extra={"document_id": str(document_id)})
            service.mark_failed(document_id, str(exc))
    finally:
        db.close()

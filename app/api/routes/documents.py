"""Document endpoints.

Upload and re-index both return immediately (status "processing") and run
ingestion in a FastAPI BackgroundTask via
app.services.document_service.run_ingestion_job — see that function's
docstring. Route handlers are plain `def`, not `async def`: everything
they do (reading the uploaded file, synchronous DB calls) is blocking, so
running them in FastAPI's threadpool (the default for sync routes) is
correct here rather than awaiting inside the shared event loop.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.schemas.document import DocumentCreateResponse, DocumentRead
from app.services.document_service import DocumentService, run_ingestion_job
from app.services.errors import ValidationError

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=DocumentCreateResponse, status_code=status.HTTP_201_CREATED)
def upload_document(
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    source_type: str = Form(...),
    equipment_id: str | None = Form(None),
    plant_id: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    uploaded_by: str = Depends(get_current_user),
) -> DocumentCreateResponse:
    file_bytes = file.file.read()
    if not file_bytes:
        raise ValidationError("Uploaded file is empty", detail={"filename": file.filename})

    service = DocumentService(db)
    document = service.create_document(
        title=title,
        source_type=source_type,
        equipment_id=equipment_id,
        plant_id=plant_id,
        uploaded_by=uploaded_by,
        file_bytes=file_bytes,
        filename=file.filename or "upload",
    )
    background_tasks.add_task(run_ingestion_job, document.id)
    return DocumentCreateResponse(document_id=document.id, status=document.status)


@router.get("/{document_id}", response_model=DocumentRead)
def get_document(document_id: UUID, db: Session = Depends(get_db)) -> DocumentRead:
    document = DocumentService(db).get_document(document_id)
    return DocumentRead.model_validate(document)


@router.get("", response_model=list[DocumentRead])
def list_documents(
    equipment_id: str | None = None,
    plant_id: str | None = None,
    status_: str | None = Query(None, alias="status"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[DocumentRead]:
    documents = DocumentService(db).list_documents(
        equipment_id=equipment_id, plant_id=plant_id, status=status_, limit=limit, offset=offset
    )
    return [DocumentRead.model_validate(d) for d in documents]


@router.post("/{document_id}/reindex", response_model=DocumentCreateResponse)
def reindex_document(
    document_id: UUID, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
) -> DocumentCreateResponse:
    document = DocumentService(db).reindex_document(document_id)
    background_tasks.add_task(run_ingestion_job, document.id)
    return DocumentCreateResponse(document_id=document.id, status=document.status)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def archive_document(document_id: UUID, db: Session = Depends(get_db)) -> None:
    DocumentService(db).archive_document(document_id)

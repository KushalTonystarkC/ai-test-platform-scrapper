"""Document REST endpoints — thin adapters over DocumentService."""

from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, File, Form, Query, UploadFile

from app.core.dependencies import DbSession, DocumentServiceDep, TaskDispatcherDep
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.models.enums import DocumentStatus, DocumentType
from app.schemas.document import (
    DocumentChunkListResponse,
    DocumentChunkRead,
    DocumentListResponse,
    DocumentProcessResponse,
    DocumentRead,
    DocumentUploadMeta,
)
from app.workers.runner import run_document_processing
from app.workers.tasks import InMemoryTaskDispatcher

logger = get_logger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


async def _spawn_document_processing(document_id: uuid.UUID) -> None:
    """Fire-and-forget wrapper so HTTP request lifecycle cannot roll back work."""
    try:
        await run_document_processing(document_id)
    except Exception:
        logger.exception(
            "background_process_unhandled",
            document_id=str(document_id),
        )

@router.post("/upload", response_model=DocumentRead, status_code=201)
async def upload_document(
    service: DocumentServiceDep,
    file: UploadFile = File(...),
    exam_id: uuid.UUID = Form(...),
    title: str = Form(...),
    document_type: DocumentType = Form(...),
    metadata: str = Form(default="{}"),
) -> DocumentRead:
    try:
        meta_dict = json.loads(metadata) if metadata else {}
        if not isinstance(meta_dict, dict):
            raise ValueError("metadata must be a JSON object")
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValidationError(f"Invalid metadata JSON: {exc}") from exc

    data = await file.read()
    upload_meta = DocumentUploadMeta(
        exam_id=exam_id,
        title=title,
        document_type=document_type,
        metadata=meta_dict,
    )
    document = await service.upload(
        meta=upload_meta,
        filename=file.filename or "upload.pdf",
        content_type=file.content_type or "application/pdf",
        data=data,
    )
    return DocumentRead.model_validate(document)


@router.post("/{document_id}/process", response_model=DocumentProcessResponse)
async def process_document(
    document_id: uuid.UUID,
    service: DocumentServiceDep,
    dispatcher: TaskDispatcherDep,
    session: DbSession,
) -> DocumentProcessResponse:
    """Queue asynchronous knowledge-base generation for a document."""
    await service.mark_processing(document_id)
    # Commit BEFORE spawning work so status=PROCESSING is visible to GET,
    # and so the request session cannot roll back / overwrite worker commits.
    await session.commit()
    session.expunge_all()

    task_id = await dispatcher.enqueue_document_processing(document_id)

    if isinstance(dispatcher, InMemoryTaskDispatcher):
        asyncio.create_task(
            _spawn_document_processing(document_id),
            name=f"process-doc-{document_id}",
        )

    logger.info(
        "document_process_queued",
        document_id=str(document_id),
        task_id=task_id,
    )
    return DocumentProcessResponse(
        document_id=document_id,
        status=DocumentStatus.PROCESSING,
        message=f"Processing queued (task_id={task_id})",
    )


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    service: DocumentServiceDep,
    exam_id: uuid.UUID | None = None,
    status: DocumentStatus | None = None,
    document_type: DocumentType | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> DocumentListResponse:
    items, total = await service.list(
        exam_id=exam_id,
        status=status,
        document_type=document_type,
        limit=limit,
        offset=offset,
    )
    return DocumentListResponse(
        items=[DocumentRead.model_validate(d) for d in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: uuid.UUID,
    service: DocumentServiceDep,
) -> DocumentRead:
    document = await service.get(document_id)
    return DocumentRead.model_validate(document)


@router.get("/{document_id}/chunks", response_model=DocumentChunkListResponse)
async def list_chunks(
    document_id: uuid.UUID,
    service: DocumentServiceDep,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> DocumentChunkListResponse:
    items, total = await service.list_chunks(document_id, limit=limit, offset=offset)
    return DocumentChunkListResponse(
        items=[DocumentChunkRead.model_validate(c) for c in items],
        total=total,
        limit=limit,
        offset=offset,
    )

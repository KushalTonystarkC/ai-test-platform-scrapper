"""Background worker entrypoints that call the service layer."""

from __future__ import annotations

import uuid

from app.core.logging import get_logger
from app.database.session import get_session_factory

logger = get_logger(__name__)


async def run_document_processing(document_id: uuid.UUID) -> None:
    """
    Worker entrypoint: open a fresh DB session and process the document.

    Always commits after `process_document` returns or raises so that a
    FAILED status written inside the service is persisted (not rolled back).
    """
    from app.core.dependencies import get_container

    session_factory = get_session_factory()
    container = get_container()
    async with session_factory() as session:
        service = container.build_document_service(session)
        try:
            await service.process_document(document_id)
            await session.commit()
        except Exception:
            logger.exception(
                "worker_document_processing_failed",
                document_id=str(document_id),
            )
            try:
                await session.commit()
            except Exception:
                await session.rollback()
                raise

"""Task dispatcher abstraction — swap Celery/Dramatiq without touching services."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

# Signature: async callable receiving document_id
DocumentProcessHandler = Callable[[uuid.UUID], Awaitable[Any]]


class TaskDispatcher(ABC):
    """Abstract async job queue for long-running work."""

    @abstractmethod
    async def enqueue_document_processing(self, document_id: uuid.UUID) -> str:
        """
        Schedule document processing.

        Returns a task/job identifier.
        """


class InMemoryTaskDispatcher(TaskDispatcher):
    """
    Development dispatcher.

    Does NOT run work itself — the HTTP layer registers a FastAPI BackgroundTasks
    callback via `set_runner`. Production backends (Celery, Dramatiq) ignore this.
    """

    def __init__(self) -> None:
        self._runner: DocumentProcessHandler | None = None

    def set_runner(self, runner: DocumentProcessHandler) -> None:
        self._runner = runner

    async def enqueue_document_processing(self, document_id: uuid.UUID) -> str:
        task_id = f"inmem-{document_id}"
        if self._runner is None:
            logger.warning(
                "in_memory_dispatcher_no_runner",
                document_id=str(document_id),
                hint="Caller must schedule the runner via BackgroundTasks",
            )
            return task_id
        # Runner is invoked by the API layer's BackgroundTasks; this method
        # only issues the task id for contract parity with queue backends.
        logger.info("task_enqueued", backend="in_memory", task_id=task_id)
        return task_id


class CeleryTaskDispatcher(TaskDispatcher):
    """
    Placeholder for Celery integration.

    Wire `app.workers.tasks.process_document.delay(str(document_id))` when Celery
    is added as an optional dependency — services remain unchanged.
    """

    async def enqueue_document_processing(self, document_id: uuid.UUID) -> str:
        raise NotImplementedError(
            "Celery backend is not configured. Set TASK_BACKEND=in_memory "
            "or implement CeleryTaskDispatcher with a real broker."
        )


def create_task_dispatcher(backend: str) -> TaskDispatcher:
    name = backend.lower().strip()
    if name in {"in_memory", "in-memory", "memory"}:
        return InMemoryTaskDispatcher()
    if name == "celery":
        return CeleryTaskDispatcher()
    raise ValueError(f"Unknown task backend: {backend}")

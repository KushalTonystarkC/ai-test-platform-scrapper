"""Application dependency injection container and FastAPI Depends helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.database.session import get_db_session
from app.providers.chunking.semantic import SemanticChunker
from app.providers.embedding.base import EmbeddingProvider
from app.providers.embedding.factory import create_embedding_provider
from app.providers.llm.base import LLMProvider
from app.providers.llm.factory import create_llm_provider
from app.providers.pdf.pypdf_extractor import PyPDFExtractor
from app.search.service import SearchService
from app.services.document import DocumentService
from app.services.exam import ExamService
from app.utils.storage import LocalFileStorage
from app.workers.tasks import (
    InMemoryTaskDispatcher,
    TaskDispatcher,
    create_task_dispatcher,
)


@dataclass
class AppContainer:
    """Holds long-lived, swappable infrastructure dependencies."""

    settings: Settings
    llm: LLMProvider
    embeddings: EmbeddingProvider
    storage: LocalFileStorage
    pdf_extractor: PyPDFExtractor
    chunker: SemanticChunker
    task_dispatcher: TaskDispatcher

    def build_document_service(self, session: AsyncSession) -> DocumentService:
        return DocumentService(
            session,
            storage=self.storage,
            pdf_extractor=self.pdf_extractor,
            chunker=self.chunker,
            llm=self.llm,
            embeddings=self.embeddings,
            settings=self.settings,
        )

    def build_exam_service(self, session: AsyncSession) -> ExamService:
        return ExamService(session)

    def build_search_service(self, session: AsyncSession) -> SearchService:
        return SearchService(session, self.embeddings, self.settings)


_container: AppContainer | None = None


def init_container(settings: Settings | None = None) -> AppContainer:
    global _container
    settings = settings or get_settings()
    _container = AppContainer(
        settings=settings,
        llm=create_llm_provider(settings),
        embeddings=create_embedding_provider(settings),
        storage=LocalFileStorage(settings),
        pdf_extractor=PyPDFExtractor(),
        chunker=SemanticChunker(settings),
        task_dispatcher=create_task_dispatcher(settings.task_backend),
    )
    return _container


def get_container() -> AppContainer:
    if _container is None:
        return init_container()
    return _container


def reset_container() -> None:
    global _container
    _container = None


# --- FastAPI dependency providers ---

DbSession = Annotated[AsyncSession, Depends(get_db_session)]


async def get_document_service(session: DbSession) -> DocumentService:
    return get_container().build_document_service(session)


async def get_exam_service(session: DbSession) -> ExamService:
    return get_container().build_exam_service(session)


async def get_search_service(session: DbSession) -> SearchService:
    return get_container().build_search_service(session)


def get_task_dispatcher() -> TaskDispatcher:
    return get_container().task_dispatcher


DocumentServiceDep = Annotated[DocumentService, Depends(get_document_service)]
ExamServiceDep = Annotated[ExamService, Depends(get_exam_service)]
SearchServiceDep = Annotated[SearchService, Depends(get_search_service)]
TaskDispatcherDep = Annotated[TaskDispatcher, Depends(get_task_dispatcher)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.router import api_router
from app.core.config import get_settings
from app.core.dependencies import init_container, reset_container
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.database.session import dispose_db, init_db

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(
        log_level=settings.log_level,
        json_logs=settings.app_env.lower() == "production",
    )
    init_db(settings)
    init_container(settings)
    logger.info(
        "app_started",
        env=settings.app_env,
        llm=settings.llm_provider,
        embedding=settings.embedding_provider,
        task_backend=settings.task_backend,
    )
    yield
    await dispose_db()
    reset_container()
    logger.info("app_stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Question Bank Knowledge Base",
        description=(
            "Phase 1 — Document ingestion and knowledge base generation "
            "for competitive exam platforms."
        ),
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    register_exception_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


app = create_app()


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )

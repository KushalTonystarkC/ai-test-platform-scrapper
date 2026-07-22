"""SQLAlchemy async engine and session management."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, get_settings


def create_engine(settings: Settings | None = None) -> AsyncEngine:
    settings = settings or get_settings()
    return create_async_engine(
        settings.database_url,
        echo=settings.database_echo,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


# Module-level singletons wired at app startup
engine: AsyncEngine | None = None
SessionLocal: async_sessionmaker[AsyncSession] | None = None


def init_db(settings: Settings | None = None) -> None:
    global engine, SessionLocal
    engine = create_engine(settings)
    SessionLocal = create_session_factory(engine)


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the live session factory (avoids stale imported None bindings)."""
    if SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return SessionLocal


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_db() -> None:
    global engine, SessionLocal
    if engine is not None:
        await engine.dispose()
    engine = None
    SessionLocal = None

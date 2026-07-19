"""Async database session factory.

Spec reference: §2.2 (SQLModel + asyncpg), §9.3 (Depends(get_async_session)).
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from sqlmodel import SQLModel  # noqa: F401
from app.models import *  # noqa: F401, F403 — ensures all models registered

# Create the async engine
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=(settings.APP_ENV == "development"),
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
)

# Session factory
async_session_factory = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async DB session.

    Usage in routes:
        session: AsyncSession = Depends(get_async_session)
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

"""Async SQLAlchemy database session for the cloud control plane.

SQLite (aiosqlite) is used for local/standalone installations; PostgreSQL
(asyncpg) is used for the hosted multi-user control plane. Select via
``EB_DATABASE_URL``.
"""

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.app.core.settings import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Create all tables. Migrations (Alembic) are preferred in production."""
    from backend.app.models.base import Base  # noqa: F401  (registers models)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

"""
SONIC-REDA — PostgreSQL & SQLite Async Database Session Manager
==================================================================
Manages database connection pools, async sessions, and schema initialization.
Supports PostgreSQL (production) and SQLite+aiosqlite (development/testing).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from sonic.db.models import Base
from sonic.logger import get_logger

logger = get_logger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_database_url() -> str:
    """Resolve database URL with async driver."""
    raw_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    if raw_url:
        if raw_url.startswith("postgres://"):
            return raw_url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif raw_url.startswith("postgresql://") and not raw_url.startswith("postgresql+asyncpg://"):
            return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return raw_url
    # Default to async SQLite for local/offline execution
    return "sqlite+aiosqlite:///./sonic_data.db"


def get_engine() -> AsyncEngine:
    """Get or create singleton AsyncEngine."""
    global _engine
    if _engine is None:
        db_url = get_database_url()
        _engine = create_async_engine(
            db_url,
            echo=False,
            future=True,
        )
        logger.info("database_engine_initialized", db_backend=db_url.split("://")[0])
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create sessionmaker."""
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def init_db() -> None:
    """Initialize database schema and tables."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("database_schema_initialized")


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency for database sessions."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

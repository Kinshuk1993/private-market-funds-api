"""
Database session management.

Provides an async SQLAlchemy engine and a dependency-injectable session factory
for use across the application via FastAPI's ``Depends()`` mechanism.
"""

from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# ── Engine creation (PostgreSQL or SQLite) ──
if settings.USE_SQLITE:
    # In-memory SQLite for zero-dependency testing.
    # StaticPool ensures every connection shares the SAME in-memory database;
    # without it each connection would get its own empty database.
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite does not enforce FK constraints by default — enable them.
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

else:
    # ── Async engine with production-grade pool settings ──
    # Pool configuration prevents connection starvation under load and
    # automatically recycles stale connections to guard against PostgreSQL
    # idle-timeout eviction.
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        future=True,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_recycle=settings.DB_POOL_RECYCLE,
        pool_pre_ping=True,  # Issues a lightweight SELECT 1 before handing out a connection
    )

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an async database session.

    The session is automatically closed when the request finishes,
    ensuring no leaked connections back to the pool.
    """
    async with AsyncSessionLocal() as session:
        yield session

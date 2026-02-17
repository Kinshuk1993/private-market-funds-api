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
    # StaticPool forces every connection to share the SAME in-memory database;
    # without it, each async connection would get its own empty database,
    # effectively losing all data between operations.
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite does not enforce FK constraints by default — enable them.
    # We listen on the *sync* engine because aiosqlite delegates to a sync
    # connection under the hood; the async engine doesn't fire "connect".
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

else:
    # Async PostgreSQL engine with connection pool settings.
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
    # expire_on_commit=False is critical for async SQLAlchemy: without it,
    # accessing an attribute after commit() triggers a lazy load, which
    # fails because lazy loads require a sync I/O call.
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

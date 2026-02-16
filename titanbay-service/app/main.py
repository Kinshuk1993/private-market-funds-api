"""
Titanbay Private Markets API — Application entry-point.

Initialises the FastAPI application, registers middleware, exception handlers,
routers, and manages the application lifecycle (DB table creation on startup).
"""

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy import text
from sqlmodel import SQLModel

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.exceptions import add_exception_handlers
from app.db.session import AsyncSessionLocal, engine
from app.middleware import RequestIDMiddleware, RequestTimingMiddleware

# ── Structured logging configuration ──
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Application lifespan  (replaces deprecated @app.on_event)
# ────────────────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Manages startup / shutdown lifecycle events.

    Startup:
      - Imports all SQLModel table models so metadata is populated.
      - Creates all tables that do not yet exist (safe for re-runs).

    Shutdown:
      - Disposes of the connection pool to release DB connections cleanly.
    """
    logger.info("Starting up — creating database tables if they do not exist")
    # Import models so SQLModel.metadata knows about them
    import app.models.fund  # noqa: F401
    import app.models.investor  # noqa: F401
    import app.models.investment  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    logger.info("Database tables ready")

    yield  # ← application is running

    logger.info("Shutting down — disposing connection pool")
    await engine.dispose()


# ────────────────────────────────────────────────────────────────────────────
# FastAPI application instance
# ────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description=(
        "RESTful API for managing private market funds, investors, "
        "and their investments."
    ),
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

# ── Middleware (order matters: outermost = first to execute) ──
# GZip compresses responses > 500 bytes — critical for reducing bandwidth
# when serving millions of global users, especially on list endpoints
# that return large JSON arrays.
app.add_middleware(GZipMiddleware, minimum_size=500)

# Request ID: injects/propagates X-Request-ID for distributed tracing
app.add_middleware(RequestIDMiddleware)

# Request timing: logs duration and adds X-Process-Time header
app.add_middleware(RequestTimingMiddleware)

# CORS: allows cross-origin requests from configured origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global error handlers ──
add_exception_handlers(app)

# ── API routers ──
app.include_router(api_router, prefix=settings.API_V1_STR)


# ── Health check ──


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Liveness / readiness probe with database connectivity check.

    Returns 200 with service metadata when healthy.  Verifies the database
    is reachable by executing a lightweight ``SELECT 1`` — without this,
    a Kubernetes readiness probe would keep routing traffic to a pod that
    has lost its DB connection, causing cascading 500 errors.
    """
    db_healthy = True
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        db_healthy = False

    status = "ok" if db_healthy else "degraded"
    return {"status": status, "version": "1.0.0", "database": db_healthy}

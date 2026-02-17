"""
Titanbay Private Markets API — Application entry-point.

Initializes the FastAPI application, registers middleware, exception handlers,
routers, and manages the application lifecycle (DB table creation on startup).
"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.openapi.docs import get_redoc_html
from sqlalchemy import text
from sqlmodel import SQLModel

from app.api.v1.api import api_router
from app.core.cache import cache
from app.core.config import settings
from app.core.exceptions import add_exception_handlers
from app.core.logging import setup_logging
from app.core.resilience import db_circuit_breaker
from app.db.session import AsyncSessionLocal, engine
from app.middleware import RequestIDMiddleware, RequestTimingMiddleware

# ── Initialise production logging (rotating files + JSON structured) ──
setup_logging()
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
      - Attempts to connect to PostgreSQL and create tables, with retry logic.
      - If the database is unreachable after all retries, the app starts in
        degraded mode (health check will report ``database: false``).

    Shutdown:
      - Disposes of the connection pool to release DB connections cleanly.
    """
    # Import models so SQLModel.metadata knows about them.
    # SQLModel (and SQLAlchemy) only learns about table classes when their
    # module is imported.  Without these imports, create_all() would create
    # an empty database with no tables.
    import app.models.fund  # noqa: F401
    import app.models.investment  # noqa: F401
    import app.models.investor  # noqa: F401

    max_retries = 5
    retry_delay = 2  # seconds (doubles each attempt)

    for attempt in range(1, max_retries + 1):
        try:
            logger.info("Connecting to database (attempt %d/%d)…", attempt, max_retries)
            async with engine.begin() as conn:
                await conn.run_sync(SQLModel.metadata.create_all)
            logger.info("Database tables ready")
            break
        except Exception as exc:
            if attempt < max_retries:
                logger.warning(
                    "Database connection failed (attempt %d/%d): %s — " "retrying in %ds…",
                    attempt,
                    max_retries,
                    exc,
                    retry_delay,
                )
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # exponential back-off
            else:
                logger.error(
                    "Could not connect to database after %d attempts. "
                    "The application will start in DEGRADED mode — all "
                    "database-dependent endpoints will return 500 errors "
                    "until the database becomes available. Last error: %s",
                    max_retries,
                    exc,
                )

    # asynccontextmanager protocol: everything above `yield` runs at startup,
    # everything below it runs at shutdown.  FastAPI calls this as:
    #   async with lifespan(app):  # startup
    #       ... serve requests ...
    #   # shutdown code runs after the `with` block exits
    yield

    logger.info("Shutting down — disposing connection pool")
    await engine.dispose()


# ────────────────────────────────────────────────────────────────────────────
# FastAPI application instance
# ────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description=(
        "RESTful API for managing private market funds, investors, " "and their investments."
    ),
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    redoc_url=None,  # Disabled default — custom route below uses a working CDN
    lifespan=lifespan,
)


# ── Custom ReDoc route — default cdn.redoc.ly is blocked by Chrome ORB ──
@app.get("/redoc", include_in_schema=False)
async def custom_redoc_html():
    """Serve ReDoc using the unpkg CDN which has proper CORS headers."""
    return get_redoc_html(
        openapi_url=app.openapi_url or f"{settings.API_V1_STR}/openapi.json",
        title=f"{settings.PROJECT_NAME} — ReDoc",
        redoc_js_url="https://unpkg.com/redoc@latest/bundles/redoc.standalone.js",
    )


# ── Middleware (order matters: outermost = first to execute) ──
# GZip compresses responses > 500 bytes, reducing bandwidth on list endpoints.
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

    Also reports circuit breaker state and cache statistics for operational
    visibility.
    """
    db_healthy = True
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        db_healthy = False

    status = "ok" if db_healthy else "degraded"
    return {
        "status": status,
        "version": "1.0.0",
        "database": db_healthy,
        "circuit_breaker": db_circuit_breaker.get_status(),
        "cache": cache.get_stats(),
    }

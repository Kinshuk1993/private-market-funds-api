"""
Application configuration module.

Loads settings from environment variables (or .env file) using pydantic-settings.
All sensitive values (DB credentials) come from environment — never hardcoded.
"""

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central configuration for the Titanbay Private Markets API.

    Environment variables are loaded automatically from .env if present.
    In production, these should be injected via the container orchestrator
    (e.g., Kubernetes Secrets, AWS Parameter Store).
    """

    PROJECT_NAME: str = "Titanbay Private Markets API"
    API_V1_STR: str = "/api/v1"

    # ── SQLite mode (no external DB required) ──
    USE_SQLITE: bool = False

    # ── PostgreSQL connection parameters ──
    # Default to empty string so USE_SQLITE=true works without
    # requiring dummy PostgreSQL env vars to be set.
    # When USE_SQLITE is False (production), the model_validator below
    # enforces that all four PG fields are populated — preserving the
    # fail-fast behaviour that prevents silent misconfiguration.
    POSTGRES_USER: str = ""
    POSTGRES_PASSWORD: str = ""
    POSTGRES_SERVER: str = ""
    POSTGRES_DB: str = ""
    POSTGRES_PORT: int = 5432

    @model_validator(mode="after")
    def _require_pg_credentials_unless_sqlite(self) -> "Settings":
        """Fail fast if PostgreSQL credentials are missing in production mode.

        Without this guard, defaulting PG fields to ``""`` would let the app
        silently start with invalid credentials and enter degraded mode
        instead of crashing immediately with a clear error.
        """
        if not self.USE_SQLITE:
            missing = [
                name
                for name in (
                    "POSTGRES_USER",
                    "POSTGRES_PASSWORD",
                    "POSTGRES_SERVER",
                    "POSTGRES_DB",
                )
                if not getattr(self, name)
            ]
            if missing:
                vars_list = ", ".join(missing)
                raise ValueError(
                    f"PostgreSQL mode requires these environment variables: "
                    f"{vars_list}.\n\n"
                    f"Set them via one of these methods:\n\n"
                    f"  1. Create a .env file in the project root:\n"
                    f"       POSTGRES_USER=titanbay_user\n"
                    f"       POSTGRES_PASSWORD=titanbay_password\n"
                    f"       POSTGRES_SERVER=127.0.0.1\n"
                    f"       POSTGRES_DB=titanbay_db\n\n"
                    f"  2. Export as environment variables before starting:\n"
                    f"       export POSTGRES_USER=titanbay_user\n"
                    f"       export POSTGRES_PASSWORD=titanbay_password\n"
                    f"       export POSTGRES_SERVER=127.0.0.1\n"
                    f"       export POSTGRES_DB=titanbay_db\n\n"
                    f"  3. Pass inline when running the server:\n"
                    f"       POSTGRES_USER=titanbay_user POSTGRES_PASSWORD=titanbay_password "
                    f"POSTGRES_SERVER=127.0.0.1 POSTGRES_DB=titanbay_db "
                    f"uvicorn app.main:app\n\n"
                    f"  4. Skip PostgreSQL entirely (in-memory SQLite):\n"
                    f"       USE_SQLITE=true uvicorn app.main:app"
                )
        return self

    # ── Connection pool tuning ──
    # These govern the SQLAlchemy async engine pool.  Values below are
    # reasonable defaults for a containerised deployment behind a load balancer.
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30  # seconds to wait for a connection from the pool
    DB_POOL_RECYCLE: int = (
        1800  # seconds before a connection is recycled (avoid stale conns)
    )

    # ── CORS ──
    # Comma-separated list of allowed origins. "*" in dev, restrict in prod.
    CORS_ORIGINS: str = "*"

    # ── Misc ──
    DEBUG: bool = False

    @property
    def DATABASE_URL(self) -> str:
        """Construct the async database DSN.

        Returns an in-memory SQLite URL when ``USE_SQLITE`` is enabled,
        otherwise a PostgreSQL DSN for asyncpg.
        """
        if self.USE_SQLITE:
            return "sqlite+aiosqlite://"
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

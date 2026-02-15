"""
Application configuration module.

Loads settings from environment variables (or .env file) using pydantic-settings.
All sensitive values (DB credentials) come from environment — never hardcoded.
"""

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

    # ── PostgreSQL connection parameters ──
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_SERVER: str
    POSTGRES_DB: str
    POSTGRES_PORT: int = 5432

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
        """Construct the async PostgreSQL DSN for asyncpg."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

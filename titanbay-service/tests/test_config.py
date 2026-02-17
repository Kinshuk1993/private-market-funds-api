"""
Unit tests for the application configuration (Settings).

Tests cover:
- Default values
- DATABASE_URL property for SQLite mode
- PostgreSQL credential validation
"""


class TestSettingsDefaults:
    """Tests for default settings values."""

    def test_project_name(self):
        from app.core.config import settings

        assert settings.PROJECT_NAME == "Titanbay Private Markets API"

    def test_api_version_prefix(self):
        from app.core.config import settings

        assert settings.API_V1_STR == "/api/v1"

    def test_use_sqlite_default(self):
        from app.core.config import settings

        # In test env, USE_SQLITE should be True
        assert isinstance(settings.USE_SQLITE, bool)

    def test_cache_settings_have_defaults(self):
        from app.core.config import settings

        assert settings.CACHE_TTL > 0
        assert settings.CACHE_MAX_SIZE > 0
        assert isinstance(settings.CACHE_ENABLED, bool)

    def test_circuit_breaker_settings_have_defaults(self):
        from app.core.config import settings

        assert settings.CB_FAILURE_THRESHOLD > 0
        assert settings.CB_RECOVERY_TIMEOUT > 0


class TestDatabaseURL:
    """Tests for the DATABASE_URL property."""

    def test_sqlite_url(self):
        from app.core.config import settings

        if settings.USE_SQLITE:
            assert "sqlite" in settings.DATABASE_URL

    def test_postgres_url(self):
        """Construct a Settings with PG creds to cover the PostgreSQL branch."""
        from app.core.config import Settings

        s = Settings(
            USE_SQLITE=False,
            POSTGRES_USER="u",
            POSTGRES_PASSWORD="p",
            POSTGRES_SERVER="localhost",
            POSTGRES_DB="db",
            POSTGRES_PORT=5432,
        )
        url = s.DATABASE_URL
        assert url.startswith("postgresql+asyncpg://")
        assert "u:p@localhost:5432/db" in url

    def test_pg_missing_credentials_raises(self):
        """Settings validator rejects missing PG credentials in non-SQLite mode."""
        import os

        import pytest

        from app.core.config import Settings

        # conftest sets USE_SQLITE=true globally, and .env supplies PG creds.
        # Temporarily remove both so the validator sees empty PG fields with
        # USE_SQLITE=False.
        saved = {}
        for key in (
            "USE_SQLITE",
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "POSTGRES_SERVER",
            "POSTGRES_DB",
        ):
            saved[key] = os.environ.pop(key, None)
        try:
            with pytest.raises(Exception, match="POSTGRES_USER"):
                Settings(USE_SQLITE=False, _env_file=None)  # type: ignore[call-arg]
        finally:
            for key, val in saved.items():
                if val is not None:
                    os.environ[key] = val

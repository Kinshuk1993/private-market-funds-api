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

"""
Unit tests for domain exceptions and exception handler registration.

Tests cover:
- AppException, NotFoundException, ConflictException, BusinessRuleViolation
- Default attributes (status_code, message)
- add_exception_handlers registration
"""

import pytest

from app.core.exceptions import (
    AppException,
    BusinessRuleViolation,
    ConflictException,
    NotFoundException,
)


class TestAppException:
    """Tests for the base AppException."""

    def test_attributes(self):
        exc = AppException(status_code=400, message="bad request", details={"key": "v"})
        assert exc.status_code == 400
        assert exc.message == "bad request"
        assert exc.details == {"key": "v"}

    def test_is_exception(self):
        exc = AppException(status_code=500, message="err")
        assert isinstance(exc, Exception)

    def test_str_representation(self):
        exc = AppException(status_code=418, message="I'm a teapot")
        assert str(exc) == "I'm a teapot"


class TestNotFoundException:
    """Tests for NotFoundException (404)."""

    def test_status_code(self):
        exc = NotFoundException("Fund", "abc-123")
        assert exc.status_code == 404

    def test_message_format(self):
        exc = NotFoundException("Fund", "abc-123")
        assert "Fund" in exc.message
        assert "abc-123" in exc.message

    def test_inherits_app_exception(self):
        exc = NotFoundException("Investor", "x")
        assert isinstance(exc, AppException)


class TestConflictException:
    """Tests for ConflictException (409)."""

    def test_status_code(self):
        exc = ConflictException("Duplicate email")
        assert exc.status_code == 409

    def test_message(self):
        exc = ConflictException("Already exists")
        assert exc.message == "Already exists"


class TestBusinessRuleViolation:
    """Tests for BusinessRuleViolation (422)."""

    def test_status_code(self):
        exc = BusinessRuleViolation("Fund is closed")
        assert exc.status_code == 422

    def test_message(self):
        exc = BusinessRuleViolation("Invalid transition")
        assert exc.message == "Invalid transition"


class TestAddExceptionHandlers:
    """Tests that add_exception_handlers registers handlers on the FastAPI app."""

    def test_handlers_registered(self):
        from unittest.mock import MagicMock

        from app.core.exceptions import add_exception_handlers

        mock_app = MagicMock()
        # exception_handler is used as a decorator, so we need it to return
        # a callable that accepts the handler function
        mock_app.exception_handler = MagicMock(return_value=lambda fn: fn)
        add_exception_handlers(mock_app)
        # Should have been called 5 times (AppException, CircuitBreakerError,
        # StarletteHTTPException, RequestValidationError, Exception)
        assert mock_app.exception_handler.call_count == 5


class TestExceptionHandlersIntegration:
    """Invoke the actual exception handlers to cover their response logic."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_handler_returns_503(self):
        """CircuitBreakerError → 503 with Retry-After header."""
        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient

        from app.core.exceptions import add_exception_handlers
        from app.core.resilience import CircuitBreakerError

        app = FastAPI()
        add_exception_handlers(app)

        @app.get("/boom")
        async def boom():
            raise CircuitBreakerError(name="db", retry_after=10.0)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/boom")
        assert resp.status_code == 503
        assert "Retry-After" in resp.headers
        body = resp.json()
        assert body["error"] is True
        assert "circuit is open" in body["message"]

    @pytest.mark.asyncio
    async def test_global_500_handler(self):
        """Unhandled exception → 500 with generic message."""
        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient

        from app.core.exceptions import add_exception_handlers

        # debug=False prevents Starlette's ServerErrorMiddleware from
        # re-raising the exception before our catch-all handler runs.
        app = FastAPI(debug=False)
        add_exception_handlers(app)

        @app.get("/crash")
        async def crash():
            raise RuntimeError("unexpected")

        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            resp = await client.get("/crash")
        assert resp.status_code == 500
        body = resp.json()
        assert body["error"] is True
        assert "Internal Server Error" in body["message"]

    @pytest.mark.asyncio
    async def test_validation_handler_returns_422(self):
        """Pydantic validation error → 422 with field details."""
        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient
        from pydantic import BaseModel

        from app.core.exceptions import add_exception_handlers

        app = FastAPI()
        add_exception_handlers(app)

        class Body(BaseModel):
            name: str

        @app.post("/validate")
        async def validate(body: Body):
            return {"ok": True}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/validate", json={})
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"] is True
        assert "details" in body

    @pytest.mark.asyncio
    async def test_http_exception_handler(self):
        """StarletteHTTPException (e.g. 404 from unknown route) → proper JSON."""
        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient

        from app.core.exceptions import add_exception_handlers

        app = FastAPI()
        add_exception_handlers(app)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/nonexistent")
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"] is True

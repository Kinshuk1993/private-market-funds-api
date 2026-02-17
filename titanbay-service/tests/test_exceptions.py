"""
Unit tests for domain exceptions and exception handler registration.

Tests cover:
- AppException, NotFoundException, ConflictException, BusinessRuleViolation
- Default attributes (status_code, message)
- add_exception_handlers registration
"""

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

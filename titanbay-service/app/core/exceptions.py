"""
Global exception handlers for the FastAPI application.

Centralises error formatting so every error response follows a consistent
JSON structure::

    {
        "error": true,
        "message": "<human-readable description>"
    }

This module also defines domain-specific exceptions that the service layer
can raise without importing FastAPI's HTTPException, keeping business logic
framework-agnostic (Dependency Inversion Principle).
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Domain exceptions  (raised by service layer, caught by handlers below)
# ────────────────────────────────────────────────────────────────────────────


class AppException(Exception):
    """Base exception for all application-level errors."""

    def __init__(self, status_code: int, message: str, details: Any = None):
        self.status_code = status_code
        self.message = message
        self.details = details
        super().__init__(message)


class NotFoundException(AppException):
    """Resource not found (404)."""

    def __init__(self, resource: str, identifier: Any):
        super().__init__(
            status_code=404,
            message=f"{resource} with id '{identifier}' not found",
        )


class ConflictException(AppException):
    """Resource already exists / unique-constraint violation (409)."""

    def __init__(self, message: str):
        super().__init__(status_code=409, message=message)


class BusinessRuleViolation(AppException):
    """Business rule was violated (422)."""

    def __init__(self, message: str):
        super().__init__(status_code=422, message=message)


# ────────────────────────────────────────────────────────────────────────────
# FastAPI exception handler registration
# ────────────────────────────────────────────────────────────────────────────


def add_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers on the FastAPI application instance."""

    @app.exception_handler(AppException)
    async def app_exception_handler(
        request: Request, exc: AppException
    ) -> JSONResponse:
        """Handle domain-specific exceptions raised by the service layer."""
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": True, "message": exc.message},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """Handle standard HTTP exceptions (e.g. 404 from path-not-found)."""
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": True, "message": exc.detail},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """
        Handle Pydantic / FastAPI request-validation errors.

        Returns a 422 with a concise list of validation issues so the caller
        knows exactly which fields failed and why.
        """
        errors = []
        for err in exc.errors():
            loc = " -> ".join(str(part) for part in err["loc"])
            errors.append({"field": loc, "message": err["msg"]})
        return JSONResponse(
            status_code=422,
            content={"error": True, "message": "Validation failed", "details": errors},
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """
        Catch-all for unexpected exceptions.

        In production this should forward to an observability platform
        (e.g. Sentry, Datadog) before returning a generic 500.
        """
        logger.exception(
            "Unhandled exception on %s %s", request.method, request.url.path
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": True,
                "message": "Internal Server Error. Please contact support.",
            },
        )

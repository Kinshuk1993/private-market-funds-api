"""
Unit tests for middleware — RequestIDMiddleware and RequestTimingMiddleware.

Uses httpx.AsyncClient against a lightweight FastAPI test app to exercise
both middleware classes through their full dispatch cycle.
"""

import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.middleware import REQUEST_ID_HEADER, RequestIDMiddleware, RequestTimingMiddleware


def _make_test_app() -> FastAPI:
    """Create a minimal FastAPI app with both middleware classes."""
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(RequestTimingMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return {"ok": True}

    return app


@pytest.fixture()
def test_app():
    return _make_test_app()


# ────────────────────────────────────────────────────────────────────────────
# RequestIDMiddleware tests
# ────────────────────────────────────────────────────────────────────────────


class TestRequestIDMiddleware:
    """Tests for X-Request-ID header injection."""

    @pytest.mark.asyncio
    async def test_generates_request_id_when_absent(self, test_app):
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/test")

        assert REQUEST_ID_HEADER in resp.headers
        # Should be a valid UUID4
        request_id = resp.headers[REQUEST_ID_HEADER]
        uuid.UUID(request_id)  # raises if invalid

    @pytest.mark.asyncio
    async def test_honours_existing_request_id(self, test_app):
        custom_id = "my-trace-id-12345"
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/test", headers={REQUEST_ID_HEADER: custom_id})

        assert resp.headers[REQUEST_ID_HEADER] == custom_id


# ────────────────────────────────────────────────────────────────────────────
# RequestTimingMiddleware tests
# ────────────────────────────────────────────────────────────────────────────


class TestRequestTimingMiddleware:
    """Tests for X-Process-Time header injection."""

    @pytest.mark.asyncio
    async def test_adds_process_time_header(self, test_app):
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/test")

        assert "X-Process-Time" in resp.headers
        # Should end with "ms"
        assert resp.headers["X-Process-Time"].endswith("ms")

    @pytest.mark.asyncio
    async def test_process_time_is_positive(self, test_app):
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/test")

        time_str = resp.headers["X-Process-Time"].replace("ms", "")
        assert float(time_str) >= 0

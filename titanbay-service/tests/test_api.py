"""
Integration tests for the API endpoints using httpx AsyncClient.

These tests exercise the full FastAPI request → middleware → endpoint → service
pipeline, with mocked service layers to isolate from the database.
"""

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.exceptions import (
    BusinessRuleViolation,
    ConflictException,
    NotFoundException,
    add_exception_handlers,
)
from app.models.fund import FundStatus

from .conftest import (
    FUND_ID,
    INVESTOR_ID,
    make_fund,
    make_investment,
    make_investor,
)

# ────────────────────────────────────────────────────────────────────────────
# Test app factory
# ────────────────────────────────────────────────────────────────────────────


def _make_test_app() -> FastAPI:
    """
    Build a minimal FastAPI app with the real routers but
    NO database or lifespan — services will be injected via overrides.
    """
    from app.api.v1.api import api_router

    app = FastAPI()
    add_exception_handlers(app)
    app.include_router(api_router, prefix="/api/v1")
    return app


# ────────────────────────────────────────────────────────────────────────────
# Funds endpoint tests
# ────────────────────────────────────────────────────────────────────────────


class TestFundsEndpoints:
    """Tests for /api/v1/funds endpoints."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.app = _make_test_app()
        self.mock_service = AsyncMock()

    def _override_service(self):
        from app.api.v1.endpoints.funds import _get_fund_service

        self.app.dependency_overrides[_get_fund_service] = lambda: self.mock_service

    @pytest.mark.asyncio
    async def test_list_funds_200(self):
        self._override_service()
        fund = make_fund()
        self.mock_service.get_all_funds.return_value = [fund]

        transport = ASGITransport(app=self.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/funds")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Test Fund I"

    @pytest.mark.asyncio
    async def test_list_funds_empty(self):
        self._override_service()
        self.mock_service.get_all_funds.return_value = []

        transport = ASGITransport(app=self.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/funds")

        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_create_fund_201(self):
        self._override_service()
        created = make_fund(name="New Fund")
        self.mock_service.create_fund.return_value = created

        transport = ASGITransport(app=self.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/funds",
                json={
                    "name": "New Fund",
                    "vintage_year": 2025,
                    "target_size_usd": 100000000,
                    "status": "Fundraising",
                },
            )

        assert resp.status_code == 201
        assert resp.json()["name"] == "New Fund"

    @pytest.mark.asyncio
    async def test_create_fund_422_validation(self):
        self._override_service()

        transport = ASGITransport(app=self.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/funds",
                json={
                    "name": "",
                    "vintage_year": 2025,
                    "target_size_usd": 100000000,
                },
            )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_get_fund_200(self):
        self._override_service()
        fund = make_fund()
        self.mock_service.get_fund.return_value = fund

        transport = ASGITransport(app=self.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/v1/funds/{FUND_ID}")

        assert resp.status_code == 200
        assert resp.json()["name"] == "Test Fund I"

    @pytest.mark.asyncio
    async def test_get_fund_404(self):
        self._override_service()
        self.mock_service.get_fund.side_effect = NotFoundException("Fund", FUND_ID)

        transport = ASGITransport(app=self.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/v1/funds/{FUND_ID}")

        assert resp.status_code == 404
        assert resp.json()["error"] is True

    @pytest.mark.asyncio
    async def test_update_fund_200(self):
        self._override_service()
        updated = make_fund(name="Updated", status=FundStatus.INVESTING)
        self.mock_service.update_fund.return_value = updated

        transport = ASGITransport(app=self.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                "/api/v1/funds",
                json={
                    "id": str(FUND_ID),
                    "name": "Updated",
                    "vintage_year": 2025,
                    "target_size_usd": 200000000,
                    "status": "Investing",
                },
            )

        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated"

    @pytest.mark.asyncio
    async def test_update_fund_404(self):
        self._override_service()
        self.mock_service.update_fund.side_effect = NotFoundException("Fund", FUND_ID)

        transport = ASGITransport(app=self.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                "/api/v1/funds",
                json={
                    "id": str(FUND_ID),
                    "name": "Fund",
                    "vintage_year": 2025,
                    "target_size_usd": 1000,
                    "status": "Fundraising",
                },
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_fund_invalid_transition(self):
        self._override_service()
        self.mock_service.update_fund.side_effect = BusinessRuleViolation(
            "Invalid status transition"
        )

        transport = ASGITransport(app=self.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                "/api/v1/funds",
                json={
                    "id": str(FUND_ID),
                    "name": "Fund",
                    "vintage_year": 2025,
                    "target_size_usd": 1000,
                    "status": "Fundraising",
                },
            )

        assert resp.status_code == 422


# ────────────────────────────────────────────────────────────────────────────
# Investors endpoint tests
# ────────────────────────────────────────────────────────────────────────────


class TestInvestorsEndpoints:
    """Tests for /api/v1/investors endpoints."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.app = _make_test_app()
        self.mock_service = AsyncMock()

    def _override_service(self):
        from app.api.v1.endpoints.investors import _get_investor_service

        self.app.dependency_overrides[_get_investor_service] = lambda: self.mock_service

    @pytest.mark.asyncio
    async def test_list_investors_200(self):
        self._override_service()
        self.mock_service.get_all_investors.return_value = [make_investor()]

        transport = ASGITransport(app=self.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/investors")

        assert resp.status_code == 200
        assert len(resp.json()) == 1

    @pytest.mark.asyncio
    async def test_create_investor_201(self):
        self._override_service()
        created = make_investor(name="CalPERS", email="pe@calpers.gov")
        self.mock_service.create_investor.return_value = created

        transport = ASGITransport(app=self.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/investors",
                json={
                    "name": "CalPERS",
                    "investor_type": "Institution",
                    "email": "pe@calpers.gov",
                },
            )

        assert resp.status_code == 201
        assert resp.json()["name"] == "CalPERS"

    @pytest.mark.asyncio
    async def test_create_investor_duplicate_409(self):
        self._override_service()
        self.mock_service.create_investor.side_effect = ConflictException(
            "An investor with email 'dup@test.com' already exists"
        )

        transport = ASGITransport(app=self.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/investors",
                json={
                    "name": "Dup",
                    "investor_type": "Individual",
                    "email": "dup@test.com",
                },
            )

        assert resp.status_code == 409
        assert resp.json()["error"] is True

    @pytest.mark.asyncio
    async def test_create_investor_invalid_email_422(self):
        self._override_service()

        transport = ASGITransport(app=self.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/investors",
                json={
                    "name": "Test",
                    "investor_type": "Individual",
                    "email": "not-email",
                },
            )

        assert resp.status_code == 422


# ────────────────────────────────────────────────────────────────────────────
# Investments endpoint tests
# ────────────────────────────────────────────────────────────────────────────


class TestInvestmentsEndpoints:
    """Tests for /api/v1/funds/{fund_id}/investments endpoints."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.app = _make_test_app()
        self.mock_service = AsyncMock()

    def _override_service(self):
        from app.api.v1.endpoints.investments import _get_investment_service

        self.app.dependency_overrides[_get_investment_service] = lambda: self.mock_service

    @pytest.mark.asyncio
    async def test_list_investments_200(self):
        self._override_service()
        self.mock_service.get_investments_by_fund.return_value = [make_investment()]

        transport = ASGITransport(app=self.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/v1/funds/{FUND_ID}/investments")

        assert resp.status_code == 200
        assert len(resp.json()) == 1

    @pytest.mark.asyncio
    async def test_list_investments_fund_not_found(self):
        self._override_service()
        self.mock_service.get_investments_by_fund.side_effect = NotFoundException("Fund", FUND_ID)

        transport = ASGITransport(app=self.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/v1/funds/{FUND_ID}/investments")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_investment_201(self):
        self._override_service()
        created = make_investment()
        self.mock_service.create_investment.return_value = created

        transport = ASGITransport(app=self.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/funds/{FUND_ID}/investments",
                json={
                    "investor_id": str(INVESTOR_ID),
                    "amount_usd": 50000000,
                    "investment_date": "2025-06-15",
                },
            )

        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_create_investment_fund_not_found(self):
        self._override_service()
        self.mock_service.create_investment.side_effect = NotFoundException("Fund", FUND_ID)

        transport = ASGITransport(app=self.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/funds/{FUND_ID}/investments",
                json={
                    "investor_id": str(INVESTOR_ID),
                    "amount_usd": 50000000,
                    "investment_date": "2025-06-15",
                },
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_investment_closed_fund_422(self):
        self._override_service()
        self.mock_service.create_investment.side_effect = BusinessRuleViolation("Fund is closed")

        transport = ASGITransport(app=self.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/funds/{FUND_ID}/investments",
                json={
                    "investor_id": str(INVESTOR_ID),
                    "amount_usd": 50000000,
                    "investment_date": "2025-06-15",
                },
            )

        assert resp.status_code == 422
        assert resp.json()["error"] is True

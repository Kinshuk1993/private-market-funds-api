"""
Unit tests for InvestmentService — business logic layer.

All repository calls are mocked.  Tests cover:
- get_investments_by_fund: found fund, not found fund, cached
- create_investment: success, fund not found, fund closed,
  investor not found, IntegrityError (TOCTOU race)
"""

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.cache import cache
from app.core.exceptions import BusinessRuleViolation, NotFoundException
from app.models.fund import FundStatus
from app.schemas.investment import InvestmentCreate
from app.services.investment_service import InvestmentService

from .conftest import FUND_ID, INVESTOR_ID, make_fund, make_investment, make_investor

# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def invest_repo():
    repo = AsyncMock()
    repo.db = AsyncMock()
    return repo


@pytest.fixture()
def fund_repo():
    return AsyncMock()


@pytest.fixture()
def investor_repo():
    return AsyncMock()


@pytest.fixture()
def service(invest_repo, fund_repo, investor_repo):
    return InvestmentService(invest_repo, fund_repo, investor_repo)


# ────────────────────────────────────────────────────────────────────────────
# get_investments_by_fund
# ────────────────────────────────────────────────────────────────────────────


class TestGetInvestmentsByFund:
    """Tests for InvestmentService.get_investments_by_fund."""

    @pytest.mark.asyncio
    async def test_returns_investments_when_fund_exists(self, service, fund_repo, invest_repo):
        fund_repo.get.return_value = make_fund()
        investments = [make_investment(), make_investment(id=uuid4())]
        invest_repo.get_by_fund.return_value = investments

        result = await service.get_investments_by_fund(FUND_ID)

        assert len(result) == 2
        fund_repo.get.assert_awaited_once_with(FUND_ID)

    @pytest.mark.asyncio
    async def test_raises_not_found_when_fund_missing(self, service, fund_repo):
        fund_repo.get.return_value = None

        with pytest.raises(NotFoundException) as exc_info:
            await service.get_investments_by_fund(FUND_ID)
        assert exc_info.value.status_code == 404
        assert "Fund" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_returns_cached_investments(self, service, fund_repo, invest_repo):
        fund_repo.get.return_value = make_fund()
        cached = [make_investment()]
        cache.set(f"investments:{FUND_ID}:0:100", cached)

        result = await service.get_investments_by_fund(FUND_ID)

        invest_repo.get_by_fund.assert_not_awaited()
        assert result == cached

    @pytest.mark.asyncio
    async def test_passes_pagination(self, service, fund_repo, invest_repo):
        fund_repo.get.return_value = make_fund()
        invest_repo.get_by_fund.return_value = []

        await service.get_investments_by_fund(FUND_ID, skip=5, limit=10)

        invest_repo.get_by_fund.assert_awaited_once_with(FUND_ID, skip=5, limit=10)


# ────────────────────────────────────────────────────────────────────────────
# create_investment
# ────────────────────────────────────────────────────────────────────────────


class TestCreateInvestment:
    """Tests for InvestmentService.create_investment."""

    def _make_input(self) -> InvestmentCreate:
        return InvestmentCreate(
            investor_id=INVESTOR_ID,
            amount_usd=Decimal("50000000"),
            investment_date=date(2025, 6, 15),
        )

    @pytest.mark.asyncio
    async def test_creates_investment_successfully(
        self, service, fund_repo, investor_repo, invest_repo
    ):
        fund_repo.get.return_value = make_fund(status=FundStatus.FUNDRAISING)
        investor_repo.get.return_value = make_investor()
        expected = make_investment()
        invest_repo.create.return_value = expected

        result = await service.create_investment(FUND_ID, self._make_input())

        assert result == expected
        invest_repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fund_not_found_raises_404(self, service, fund_repo):
        fund_repo.get.return_value = None

        with pytest.raises(NotFoundException) as exc_info:
            await service.create_investment(FUND_ID, self._make_input())
        assert exc_info.value.status_code == 404
        assert "Fund" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_closed_fund_raises_business_rule(self, service, fund_repo):
        fund_repo.get.return_value = make_fund(status=FundStatus.CLOSED)

        with pytest.raises(BusinessRuleViolation) as exc_info:
            await service.create_investment(FUND_ID, self._make_input())
        assert "closed" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_investor_not_found_raises_404(self, service, fund_repo, investor_repo):
        fund_repo.get.return_value = make_fund(status=FundStatus.FUNDRAISING)
        investor_repo.get.return_value = None

        with pytest.raises(NotFoundException) as exc_info:
            await service.create_investment(FUND_ID, self._make_input())
        assert exc_info.value.status_code == 404
        assert "Investor" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_integrity_error_raises_business_rule(
        self, service, fund_repo, investor_repo, invest_repo
    ):
        fund_repo.get.return_value = make_fund(status=FundStatus.FUNDRAISING)
        investor_repo.get.return_value = make_investor()
        invest_repo.create.side_effect = IntegrityError("INSERT", {}, Exception("fk_violation"))

        with pytest.raises(BusinessRuleViolation) as exc_info:
            await service.create_investment(FUND_ID, self._make_input())
        assert exc_info.value.status_code == 422
        invest_repo.db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_investing_fund_accepts_investment(
        self, service, fund_repo, investor_repo, invest_repo
    ):
        """Funds in INVESTING status should still accept investments."""
        fund_repo.get.return_value = make_fund(status=FundStatus.INVESTING)
        investor_repo.get.return_value = make_investor()
        invest_repo.create.return_value = make_investment()

        result = await service.create_investment(FUND_ID, self._make_input())
        assert result is not None

    @pytest.mark.asyncio
    async def test_invalidates_cache_on_create(
        self, service, fund_repo, investor_repo, invest_repo
    ):
        cache.set(f"investments:{FUND_ID}:0:100", [make_investment()])

        fund_repo.get.return_value = make_fund(status=FundStatus.FUNDRAISING)
        investor_repo.get.return_value = make_investor()
        invest_repo.create.return_value = make_investment()

        await service.create_investment(FUND_ID, self._make_input())

        assert cache.get(f"investments:{FUND_ID}:0:100") is None

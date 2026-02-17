"""
Unit tests for FundService — business logic layer.

All repository calls are mocked.  Tests cover:
- get_all_funds: cache miss, cache hit
- get_fund: found, not found, cached
- create_fund: success, IntegrityError
- update_fund: success, not found, invalid status transition, IntegrityError
- _validate_status_transition: all valid/invalid combinations
"""

from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.cache import cache
from app.core.exceptions import BusinessRuleViolation, NotFoundException
from app.models.fund import FundStatus
from app.schemas.fund import FundCreate, FundUpdate
from app.services.fund_service import FundService, _validate_status_transition

from .conftest import FUND_ID, make_fund

# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def fund_repo():
    """Mocked FundRepository."""
    repo = AsyncMock()
    repo.db = AsyncMock()
    return repo


@pytest.fixture()
def fund_service(fund_repo):
    """FundService wired to the mocked repository."""
    return FundService(fund_repo)


# ────────────────────────────────────────────────────────────────────────────
# get_all_funds
# ────────────────────────────────────────────────────────────────────────────


class TestGetAllFunds:
    """Tests for FundService.get_all_funds."""

    @pytest.mark.asyncio
    async def test_returns_funds_on_cache_miss(self, fund_service, fund_repo):
        funds = [make_fund(), make_fund(id=uuid4(), name="Fund 2")]
        fund_repo.get_all.return_value = funds

        result = await fund_service.get_all_funds()

        fund_repo.get_all.assert_awaited_once_with(skip=0, limit=100)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_returns_cached_on_hit(self, fund_service, fund_repo):
        cached_funds = [make_fund()]
        cache.set("funds:list:0:100", cached_funds)

        result = await fund_service.get_all_funds()

        fund_repo.get_all.assert_not_awaited()
        assert result == cached_funds

    @pytest.mark.asyncio
    async def test_passes_pagination(self, fund_service, fund_repo):
        fund_repo.get_all.return_value = []

        await fund_service.get_all_funds(skip=10, limit=5)

        fund_repo.get_all.assert_awaited_once_with(skip=10, limit=5)


# ────────────────────────────────────────────────────────────────────────────
# get_fund
# ────────────────────────────────────────────────────────────────────────────


class TestGetFund:
    """Tests for FundService.get_fund."""

    @pytest.mark.asyncio
    async def test_returns_fund_when_found(self, fund_service, fund_repo):
        expected = make_fund()
        fund_repo.get.return_value = expected

        result = await fund_service.get_fund(FUND_ID)

        assert result == expected
        fund_repo.get.assert_awaited_once_with(FUND_ID)

    @pytest.mark.asyncio
    async def test_raises_not_found_when_missing(self, fund_service, fund_repo):
        fund_repo.get.return_value = None

        with pytest.raises(NotFoundException) as exc_info:
            await fund_service.get_fund(FUND_ID)
        assert exc_info.value.status_code == 404
        assert "Fund" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_returns_cached_fund(self, fund_service, fund_repo):
        cached_fund = make_fund()
        cache.set(f"funds:{FUND_ID}", cached_fund)

        result = await fund_service.get_fund(FUND_ID)

        fund_repo.get.assert_not_awaited()
        assert result == cached_fund


# ────────────────────────────────────────────────────────────────────────────
# create_fund
# ────────────────────────────────────────────────────────────────────────────


class TestCreateFund:
    """Tests for FundService.create_fund."""

    @pytest.mark.asyncio
    async def test_creates_fund_successfully(self, fund_service, fund_repo):
        fund_in = FundCreate(
            name="New Fund",
            vintage_year=2025,
            target_size_usd=Decimal("100000000"),
            status=FundStatus.FUNDRAISING,
        )
        expected = make_fund(name="New Fund")
        fund_repo.create.return_value = expected

        result = await fund_service.create_fund(fund_in)

        assert result == expected
        fund_repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalidates_cache_on_create(self, fund_service, fund_repo):
        # Pre-populate cache
        cache.set("funds:list:0:100", [make_fund()])

        fund_in = FundCreate(
            name="Fund",
            vintage_year=2025,
            target_size_usd=Decimal("1000"),
        )
        fund_repo.create.return_value = make_fund()

        await fund_service.create_fund(fund_in)

        # Cache should be invalidated
        assert cache.get("funds:list:0:100") is None

    @pytest.mark.asyncio
    async def test_integrity_error_raises_business_rule(self, fund_service, fund_repo):
        fund_repo.create.side_effect = IntegrityError("INSERT", {}, Exception("constraint"))

        fund_in = FundCreate(
            name="Fund",
            vintage_year=2025,
            target_size_usd=Decimal("1000"),
        )

        with pytest.raises(BusinessRuleViolation) as exc_info:
            await fund_service.create_fund(fund_in)
        assert exc_info.value.status_code == 422
        fund_repo.db.rollback.assert_awaited_once()


# ────────────────────────────────────────────────────────────────────────────
# update_fund
# ────────────────────────────────────────────────────────────────────────────


class TestUpdateFund:
    """Tests for FundService.update_fund."""

    @pytest.mark.asyncio
    async def test_updates_fund_successfully(self, fund_service, fund_repo):
        existing = make_fund(status=FundStatus.FUNDRAISING)
        fund_repo.get.return_value = existing
        updated = make_fund(
            name="Updated", target_size_usd=Decimal("200000000"), status=FundStatus.INVESTING
        )
        fund_repo.update.return_value = updated

        fund_update = FundUpdate(
            id=FUND_ID,
            name="Updated",
            vintage_year=2025,
            target_size_usd=Decimal("200000000"),
            status=FundStatus.INVESTING,
        )

        result = await fund_service.update_fund(fund_update)
        assert result == updated

    @pytest.mark.asyncio
    async def test_not_found_raises_exception(self, fund_service, fund_repo):
        fund_repo.get.return_value = None

        fund_update = FundUpdate(
            id=FUND_ID,
            name="Fund",
            vintage_year=2025,
            target_size_usd=Decimal("1000"),
            status=FundStatus.FUNDRAISING,
        )

        with pytest.raises(NotFoundException):
            await fund_service.update_fund(fund_update)

    @pytest.mark.asyncio
    async def test_invalid_status_transition_raises(self, fund_service, fund_repo):
        existing = make_fund(status=FundStatus.CLOSED)
        fund_repo.get.return_value = existing

        fund_update = FundUpdate(
            id=FUND_ID,
            name="Fund",
            vintage_year=2025,
            target_size_usd=Decimal("1000"),
            status=FundStatus.FUNDRAISING,  # Closed → Fundraising is invalid
        )

        with pytest.raises(BusinessRuleViolation, match="Invalid status transition"):
            await fund_service.update_fund(fund_update)

    @pytest.mark.asyncio
    async def test_integrity_error_on_update(self, fund_service, fund_repo):
        existing = make_fund(status=FundStatus.FUNDRAISING)
        fund_repo.get.return_value = existing
        fund_repo.update.side_effect = IntegrityError("UPDATE", {}, Exception("constraint"))

        fund_update = FundUpdate(
            id=FUND_ID,
            name="Fund",
            vintage_year=2025,
            target_size_usd=Decimal("1000"),
            status=FundStatus.FUNDRAISING,
        )

        with pytest.raises(BusinessRuleViolation):
            await fund_service.update_fund(fund_update)
        fund_repo.db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalidates_cache_on_update(self, fund_service, fund_repo):
        cache.set("funds:list:0:100", [make_fund()])
        cache.set(f"funds:{FUND_ID}", make_fund())

        existing = make_fund(status=FundStatus.FUNDRAISING)
        fund_repo.get.return_value = existing
        fund_repo.update.return_value = existing

        fund_update = FundUpdate(
            id=FUND_ID,
            name="Fund",
            vintage_year=2025,
            target_size_usd=Decimal("1000"),
            status=FundStatus.INVESTING,
        )

        await fund_service.update_fund(fund_update)

        assert cache.get("funds:list:0:100") is None
        assert cache.get(f"funds:{FUND_ID}") is None


# ────────────────────────────────────────────────────────────────────────────
# _validate_status_transition
# ────────────────────────────────────────────────────────────────────────────


class TestValidateStatusTransition:
    """Tests for the module-level status transition validator."""

    # ── Valid transitions ──

    @pytest.mark.parametrize(
        "current,requested",
        [
            (FundStatus.FUNDRAISING, FundStatus.FUNDRAISING),  # no-op
            (FundStatus.FUNDRAISING, FundStatus.INVESTING),
            (FundStatus.FUNDRAISING, FundStatus.CLOSED),
            (FundStatus.INVESTING, FundStatus.INVESTING),  # no-op
            (FundStatus.INVESTING, FundStatus.CLOSED),
            (FundStatus.CLOSED, FundStatus.CLOSED),  # no-op
        ],
    )
    def test_valid_transition(self, current, requested):
        # Should NOT raise
        _validate_status_transition(current, requested)

    # ── Invalid transitions ──

    @pytest.mark.parametrize(
        "current,requested",
        [
            (FundStatus.INVESTING, FundStatus.FUNDRAISING),  # backwards
            (FundStatus.CLOSED, FundStatus.FUNDRAISING),  # backwards from terminal
            (FundStatus.CLOSED, FundStatus.INVESTING),  # backwards from terminal
        ],
    )
    def test_invalid_transition(self, current, requested):
        with pytest.raises(BusinessRuleViolation, match="Invalid status transition"):
            _validate_status_transition(current, requested)

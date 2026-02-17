"""
Unit tests for InvestorService — business logic layer.

All repository calls are mocked.  Tests cover:
- get_all_investors: cache miss, cache hit, pagination
- create_investor: success, duplicate email pre-check, TOCTOU race
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.cache import cache
from app.core.exceptions import ConflictException
from app.models.investor import InvestorType
from app.schemas.investor import InvestorCreate
from app.services.investor_service import InvestorService

from .conftest import make_investor

# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def investor_repo():
    """Mocked InvestorRepository."""
    repo = AsyncMock()
    repo.db = AsyncMock()
    return repo


@pytest.fixture()
def investor_service(investor_repo):
    """InvestorService wired to the mocked repository."""
    return InvestorService(investor_repo)


# ────────────────────────────────────────────────────────────────────────────
# get_all_investors
# ────────────────────────────────────────────────────────────────────────────


class TestGetAllInvestors:
    """Tests for InvestorService.get_all_investors."""

    @pytest.mark.asyncio
    async def test_returns_investors_on_cache_miss(self, investor_service, investor_repo):
        investors = [make_investor(), make_investor(id=uuid4(), email="b@test.com")]
        investor_repo.get_all.return_value = investors

        result = await investor_service.get_all_investors()

        investor_repo.get_all.assert_awaited_once_with(skip=0, limit=100)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_returns_cached_on_hit(self, investor_service, investor_repo):
        cached = [make_investor()]
        cache.set("investors:list:0:100", cached)

        result = await investor_service.get_all_investors()

        investor_repo.get_all.assert_not_awaited()
        assert result == cached

    @pytest.mark.asyncio
    async def test_passes_pagination(self, investor_service, investor_repo):
        investor_repo.get_all.return_value = []
        await investor_service.get_all_investors(skip=5, limit=10)
        investor_repo.get_all.assert_awaited_once_with(skip=5, limit=10)


# ────────────────────────────────────────────────────────────────────────────
# create_investor
# ────────────────────────────────────────────────────────────────────────────


class TestCreateInvestor:
    """Tests for InvestorService.create_investor."""

    @pytest.mark.asyncio
    async def test_creates_investor_successfully(self, investor_service, investor_repo):
        investor_repo.get_by_email.return_value = None
        expected = make_investor(name="CalPERS", email="pe@calpers.gov")
        investor_repo.create.return_value = expected

        investor_in = InvestorCreate(
            name="CalPERS",
            investor_type=InvestorType.INSTITUTION,
            email="pe@calpers.gov",
        )

        result = await investor_service.create_investor(investor_in)

        assert result == expected
        investor_repo.get_by_email.assert_awaited_once_with("pe@calpers.gov")
        investor_repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_duplicate_email_raises_conflict(self, investor_service, investor_repo):
        investor_repo.get_by_email.return_value = make_investor()

        investor_in = InvestorCreate(
            name="Duplicate",
            investor_type=InvestorType.INDIVIDUAL,
            email="test@example.com",
        )

        with pytest.raises(ConflictException) as exc_info:
            await investor_service.create_investor(investor_in)
        assert exc_info.value.status_code == 409
        assert "already exists" in exc_info.value.message
        investor_repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_toctou_race_catches_integrity_error(self, investor_service, investor_repo):
        """
        Even if get_by_email returns None (pre-check passes), a concurrent
        insert could cause IntegrityError. The service should catch it and
        raise ConflictException.
        """
        investor_repo.get_by_email.return_value = None
        investor_repo.create.side_effect = IntegrityError(
            "INSERT", {}, Exception("unique_violation")
        )

        investor_in = InvestorCreate(
            name="Race Condition",
            investor_type=InvestorType.INSTITUTION,
            email="race@test.com",
        )

        with pytest.raises(ConflictException) as exc_info:
            await investor_service.create_investor(investor_in)
        assert exc_info.value.status_code == 409
        investor_repo.db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalidates_cache_on_create(self, investor_service, investor_repo):
        cache.set("investors:list:0:100", [make_investor()])

        investor_repo.get_by_email.return_value = None
        investor_repo.create.return_value = make_investor()

        investor_in = InvestorCreate(
            name="New",
            investor_type=InvestorType.INDIVIDUAL,
            email="new@test.com",
        )

        await investor_service.create_investor(investor_in)

        assert cache.get("investors:list:0:100") is None

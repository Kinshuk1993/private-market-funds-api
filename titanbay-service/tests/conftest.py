"""
Shared pytest fixtures for unit tests.

All tests run with ``USE_SQLITE=true`` and mocked dependencies so that
no real database or network I/O is needed.  This ensures tests are
fast, deterministic, and fully isolated.
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.cache import TTLCache
from app.models.fund import Fund, FundStatus
from app.models.investment import Investment
from app.models.investor import Investor, InvestorType

# ────────────────────────────────────────────────────────────────────────────
# Factory helpers — create domain objects with sensible defaults
# ────────────────────────────────────────────────────────────────────────────

FUND_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
INVESTOR_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
INVESTMENT_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
FUND_ID_2 = uuid.UUID("44444444-4444-4444-4444-444444444444")
INVESTOR_ID_2 = uuid.UUID("55555555-5555-5555-5555-555555555555")


def make_fund(
    *,
    id: uuid.UUID = FUND_ID,
    name: str = "Test Fund I",
    vintage_year: int = 2025,
    target_size_usd: Decimal = Decimal("100000000.00"),
    status: FundStatus = FundStatus.FUNDRAISING,
    created_at: datetime | None = None,
) -> Fund:
    """Create a Fund domain object with sensible test defaults."""
    return Fund(
        id=id,
        name=name,
        vintage_year=vintage_year,
        target_size_usd=target_size_usd,
        status=status,
        created_at=created_at or datetime.now(timezone.utc),
    )


def make_investor(
    *,
    id: uuid.UUID = INVESTOR_ID,
    name: str = "Test Investor",
    investor_type: InvestorType = InvestorType.INSTITUTION,
    email: str = "test@example.com",
    created_at: datetime | None = None,
) -> Investor:
    """Create an Investor domain object with sensible test defaults."""
    return Investor(
        id=id,
        name=name,
        investor_type=investor_type,
        email=email,
        created_at=created_at or datetime.now(timezone.utc),
    )


def make_investment(
    *,
    id: uuid.UUID = INVESTMENT_ID,
    fund_id: uuid.UUID = FUND_ID,
    investor_id: uuid.UUID = INVESTOR_ID,
    amount_usd: Decimal = Decimal("50000000.00"),
    investment_date: date = date(2025, 6, 15),
) -> Investment:
    """Create an Investment domain object with sensible test defaults."""
    return Investment(
        id=id,
        fund_id=fund_id,
        investor_id=investor_id,
        amount_usd=amount_usd,
        investment_date=investment_date,
    )


# ────────────────────────────────────────────────────────────────────────────
# Pytest fixtures
# ────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def mock_db():
    """A mocked AsyncSession that tracks add/commit/refresh/rollback calls."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()
    session.get = AsyncMock()
    session.merge = AsyncMock()
    session.delete = AsyncMock()
    return session


@pytest.fixture()
def test_cache():
    """A fresh TTL cache instance for test isolation."""
    return TTLCache(ttl=30.0, max_size=100, enabled=True)


@pytest.fixture()
def disabled_cache():
    """A disabled TTL cache — all operations are no-ops."""
    return TTLCache(ttl=30.0, max_size=100, enabled=False)


@pytest.fixture(autouse=True)
def _clear_global_cache():
    """
    Clear the global cache before each test to prevent cross-test pollution.

    Uses autouse=True so every test gets a clean cache automatically.
    """
    from app.core.cache import cache

    cache.clear()
    yield
    cache.clear()

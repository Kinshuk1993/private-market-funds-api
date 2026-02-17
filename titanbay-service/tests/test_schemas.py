"""
Unit tests for Pydantic schemas — validation rules, serializers, edge cases.

Tests cover:
- FundBase / FundCreate / FundUpdate / FundResponse validators
- InvestorBase / InvestorCreate / InvestorResponse validators
- InvestmentBase / InvestmentCreate / InvestmentResponse validators
- Decimal → float serialization
- Edge cases: blank names, extreme years, far-future dates
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.fund import FundStatus
from app.models.investor import InvestorType
from app.schemas.fund import FundCreate, FundResponse, FundUpdate

# ────────────────────────────────────────────────────────────────────────────
# Fund schema tests
# ────────────────────────────────────────────────────────────────────────────


class TestFundCreate:
    """Validation tests for FundCreate schema."""

    def test_valid_fund_create(self):
        fund = FundCreate(
            name="Growth Fund I",
            vintage_year=2025,
            target_size_usd=Decimal("250000000.00"),
            status=FundStatus.FUNDRAISING,
        )
        assert fund.name == "Growth Fund I"
        assert fund.vintage_year == 2025
        assert fund.target_size_usd == Decimal("250000000.00")
        assert fund.status == FundStatus.FUNDRAISING

    def test_default_status_is_fundraising(self):
        fund = FundCreate(name="Fund", vintage_year=2024, target_size_usd=Decimal("1000"))
        assert fund.status == FundStatus.FUNDRAISING

    def test_name_stripped(self):
        fund = FundCreate(
            name="  Fund ABC  ",
            vintage_year=2024,
            target_size_usd=Decimal("1000"),
        )
        assert fund.name == "Fund ABC"

    def test_blank_name_rejected(self):
        with pytest.raises(ValidationError, match="name"):
            FundCreate(name="   ", vintage_year=2024, target_size_usd=Decimal("1000"))

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError, match="name"):
            FundCreate(name="", vintage_year=2024, target_size_usd=Decimal("1000"))

    def test_vintage_year_too_low(self):
        with pytest.raises(ValidationError, match="vintage_year"):
            FundCreate(name="Fund", vintage_year=1899, target_size_usd=Decimal("1000"))

    def test_vintage_year_too_high(self):
        far_future = datetime.now().year + 6
        with pytest.raises(ValidationError, match="vintage_year"):
            FundCreate(name="Fund", vintage_year=far_future, target_size_usd=Decimal("1000"))

    def test_vintage_year_boundary_low(self):
        fund = FundCreate(name="Fund", vintage_year=1900, target_size_usd=Decimal("1000"))
        assert fund.vintage_year == 1900

    def test_vintage_year_boundary_high(self):
        max_year = datetime.now().year + 5
        fund = FundCreate(name="Fund", vintage_year=max_year, target_size_usd=Decimal("1000"))
        assert fund.vintage_year == max_year

    def test_target_size_must_be_positive(self):
        with pytest.raises(ValidationError, match="target_size_usd"):
            FundCreate(name="Fund", vintage_year=2024, target_size_usd=Decimal("0"))

    def test_target_size_negative_rejected(self):
        with pytest.raises(ValidationError, match="target_size_usd"):
            FundCreate(name="Fund", vintage_year=2024, target_size_usd=Decimal("-100"))

    def test_target_size_small_positive(self):
        fund = FundCreate(name="Fund", vintage_year=2024, target_size_usd=Decimal("0.01"))
        assert fund.target_size_usd == Decimal("0.01")

    def test_all_statuses(self):
        for status in FundStatus:
            fund = FundCreate(
                name="Fund",
                vintage_year=2024,
                target_size_usd=Decimal("1000"),
                status=status,
            )
            assert fund.status == status


class TestFundUpdate:
    """Validation tests for FundUpdate (includes id field)."""

    def test_valid_fund_update(self):
        uid = uuid4()
        fund = FundUpdate(
            id=uid,
            name="Updated Fund",
            vintage_year=2024,
            target_size_usd=Decimal("500000000"),
            status=FundStatus.INVESTING,
        )
        assert fund.id == uid
        assert fund.status == FundStatus.INVESTING

    def test_missing_id_rejected(self):
        with pytest.raises(ValidationError, match="id"):
            FundUpdate(  # type: ignore[call-arg]
                name="Fund",
                vintage_year=2024,
                target_size_usd=Decimal("1000"),
                status=FundStatus.FUNDRAISING,
            )


class TestFundResponse:
    """Serialization tests for FundResponse."""

    def test_decimal_serialized_as_float(self):
        uid = uuid4()
        resp = FundResponse(
            id=uid,
            name="Fund",
            vintage_year=2024,
            target_size_usd=Decimal("250000000.00"),
            status=FundStatus.FUNDRAISING,
            created_at=datetime.now(timezone.utc),
        )
        dumped = resp.model_dump()
        assert isinstance(dumped["target_size_usd"], float)
        assert dumped["target_size_usd"] == 250000000.00

    def test_from_attributes_mode(self):
        """FundResponse should work with ORM-style attribute access."""
        uid = uuid4()
        resp = FundResponse.model_validate(
            {
                "id": uid,
                "name": "Fund",
                "vintage_year": 2024,
                "target_size_usd": Decimal("1000"),
                "status": FundStatus.FUNDRAISING,
                "created_at": datetime.now(timezone.utc),
            }
        )
        assert resp.id == uid


# ────────────────────────────────────────────────────────────────────────────
# Investor schema tests
# ────────────────────────────────────────────────────────────────────────────


class TestInvestorCreate:
    """Validation tests for InvestorCreate schema."""

    def test_valid_investor_create(self):
        from app.schemas.investor import InvestorCreate

        inv = InvestorCreate(
            name="Goldman Sachs",
            investor_type=InvestorType.INSTITUTION,
            email="invest@gs.com",
        )
        assert inv.name == "Goldman Sachs"
        assert inv.investor_type == InvestorType.INSTITUTION
        assert str(inv.email) == "invest@gs.com"

    def test_blank_name_rejected(self):
        from app.schemas.investor import InvestorCreate

        with pytest.raises(ValidationError, match="name"):
            InvestorCreate(
                name="   ",
                investor_type=InvestorType.INDIVIDUAL,
                email="test@test.com",
            )

    def test_name_stripped(self):
        from app.schemas.investor import InvestorCreate

        inv = InvestorCreate(
            name="  CalPERS  ",
            investor_type=InvestorType.INSTITUTION,
            email="test@calpers.gov",
        )
        assert inv.name == "CalPERS"

    def test_invalid_email_rejected(self):
        from app.schemas.investor import InvestorCreate

        with pytest.raises(ValidationError, match="email"):
            InvestorCreate(
                name="Test",
                investor_type=InvestorType.INDIVIDUAL,
                email="not-an-email",
            )

    def test_all_investor_types(self):
        from app.schemas.investor import InvestorCreate

        for itype in InvestorType:
            inv = InvestorCreate(name="Test", investor_type=itype, email="test@test.com")
            assert inv.investor_type == itype


class TestInvestorResponse:
    """Serialization tests for InvestorResponse."""

    def test_response_includes_id_and_created_at(self):
        from app.schemas.investor import InvestorResponse

        uid = uuid4()
        resp = InvestorResponse(
            id=uid,
            name="Test",
            investor_type=InvestorType.INDIVIDUAL,
            email="test@test.com",
            created_at=datetime.now(timezone.utc),
        )
        assert resp.id == uid
        assert resp.created_at is not None


# ────────────────────────────────────────────────────────────────────────────
# Investment schema tests
# ────────────────────────────────────────────────────────────────────────────


class TestInvestmentCreate:
    """Validation tests for InvestmentCreate schema."""

    def test_valid_investment_create(self):
        from app.schemas.investment import InvestmentCreate

        inv = InvestmentCreate(
            investor_id=uuid4(),
            amount_usd=Decimal("50000000"),
            investment_date=date.today(),
        )
        assert inv.amount_usd == Decimal("50000000")

    def test_zero_amount_rejected(self):
        from app.schemas.investment import InvestmentCreate

        with pytest.raises(ValidationError, match="amount_usd"):
            InvestmentCreate(
                investor_id=uuid4(),
                amount_usd=Decimal("0"),
                investment_date=date.today(),
            )

    def test_negative_amount_rejected(self):
        from app.schemas.investment import InvestmentCreate

        with pytest.raises(ValidationError, match="amount_usd"):
            InvestmentCreate(
                investor_id=uuid4(),
                amount_usd=Decimal("-10000"),
                investment_date=date.today(),
            )

    def test_far_future_date_rejected(self):
        """Dates more than 1 year in the future are rejected."""
        from app.schemas.investment import InvestmentCreate

        far_future = date.today() + timedelta(days=366)
        with pytest.raises(ValidationError, match="investment_date"):
            InvestmentCreate(
                investor_id=uuid4(),
                amount_usd=Decimal("1000"),
                investment_date=far_future,
            )

    def test_date_within_one_year_accepted(self):
        from app.schemas.investment import InvestmentCreate

        near_future = date.today() + timedelta(days=364)
        inv = InvestmentCreate(
            investor_id=uuid4(),
            amount_usd=Decimal("1000"),
            investment_date=near_future,
        )
        assert inv.investment_date == near_future

    def test_past_date_accepted(self):
        from app.schemas.investment import InvestmentCreate

        past = date(2020, 1, 1)
        inv = InvestmentCreate(
            investor_id=uuid4(),
            amount_usd=Decimal("1000"),
            investment_date=past,
        )
        assert inv.investment_date == past


class TestInvestmentResponse:
    """Serialization tests for InvestmentResponse."""

    def test_decimal_serialized_as_float(self):
        from app.schemas.investment import InvestmentResponse

        resp = InvestmentResponse(
            id=uuid4(),
            fund_id=uuid4(),
            investor_id=uuid4(),
            amount_usd=Decimal("75000000.50"),
            investment_date=date.today(),
        )
        dumped = resp.model_dump()
        assert isinstance(dumped["amount_usd"], float)
        assert dumped["amount_usd"] == 75000000.50

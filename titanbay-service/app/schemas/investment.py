"""
Pydantic schemas for Investment API request / response serialisation.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InvestmentBase(BaseModel):
    """Fields common to investment creation payloads."""

    amount_usd: Decimal = Field(
        ...,
        gt=0,
        description="Investment amount in USD (must be positive)",
        examples=[50_000_000.00],
    )
    investment_date: date = Field(
        ...,
        description="Date when the investment was made (ISO-8601)",
        examples=["2024-03-15"],
    )

    @field_validator("investment_date")
    @classmethod
    def validate_investment_date_not_future(cls, v: date) -> date:
        """
        Reject investment dates more than one year in the future.

        A small buffer is allowed because commitments can be forward-dated,
        but wildly future dates are almost certainly data-entry errors.
        """
        from datetime import timedelta

        max_date = date.today() + timedelta(days=365)
        if v > max_date:
            raise ValueError(
                f"investment_date cannot be more than one year in the future (max: {max_date})"
            )
        return v


class InvestmentCreate(InvestmentBase):
    """
    Schema for ``POST /funds/{fund_id}/investments``.

    The ``fund_id`` comes from the URL path; only ``investor_id`` is in the body.
    """

    investor_id: UUID = Field(
        ...,
        description="UUID of the investor making the commitment",
    )


class InvestmentResponse(InvestmentBase):
    """Schema returned by investment endpoints."""

    id: UUID
    fund_id: UUID
    investor_id: UUID

    model_config = ConfigDict(from_attributes=True)

"""
Pydantic schemas for Fund API request / response serialisation.

Separating schemas from SQLModel table models keeps the API contract
decoupled from the persistence layer (Interface Segregation Principle).
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.fund import FundStatus


# ── Shared validation helpers ──

_CURRENT_YEAR = 2026  # Upper-bound for vintage_year validation


class FundBase(BaseModel):
    """Fields common to fund creation and update payloads."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Human-readable name of the fund",
        examples=["Titanbay Growth Fund I"],
    )
    vintage_year: int = Field(
        ...,
        description="Year the fund was established",
        examples=[2024],
    )
    target_size_usd: Decimal = Field(
        ...,
        gt=0,
        description="Target fund size in USD (must be positive)",
        examples=[250_000_000.00],
    )
    status: FundStatus = Field(
        default=FundStatus.FUNDRAISING,
        description="Lifecycle status of the fund",
    )

    @field_validator("vintage_year")
    @classmethod
    def validate_vintage_year(cls, v: int) -> int:
        """Vintage year must be a realistic calendar year."""
        if v < 1900 or v > _CURRENT_YEAR + 5:
            raise ValueError(
                f"vintage_year must be between 1900 and {_CURRENT_YEAR + 5}"
            )
        return v

    @field_validator("name")
    @classmethod
    def validate_name_not_blank(cls, v: str) -> str:
        """Reject whitespace-only names."""
        if not v.strip():
            raise ValueError("name must not be blank")
        return v.strip()


class FundCreate(FundBase):
    """
    Schema for ``POST /funds``.

    All base fields are required; ``status`` defaults to *Fundraising*.
    """

    pass


class FundUpdate(FundBase):
    """
    Schema for ``PUT /funds``.

    Per the API spec the caller sends the full resource representation
    including the ``id`` in the request body.
    """

    id: UUID = Field(
        ...,
        description="UUID of the fund to update",
    )


class FundResponse(FundBase):
    """Schema returned by all fund endpoints."""

    id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

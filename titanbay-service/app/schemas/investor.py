"""
Pydantic schemas for Investor API request / response serialisation.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.investor import InvestorType


class InvestorBase(BaseModel):
    """Fields common to investor creation payloads."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Full name of the investor or institution",
        examples=["Goldman Sachs Asset Management"],
    )
    investor_type: InvestorType = Field(
        ...,
        description="Classification: Individual, Institution, or Family Office",
    )
    email: EmailStr = Field(
        ...,
        description="Contact email address (must be unique across investors)",
        examples=["investments@gsam.com"],
    )

    @field_validator("name")
    @classmethod
    def validate_name_not_blank(cls, v: str) -> str:
        """Reject whitespace-only names."""
        if not v.strip():
            raise ValueError("name must not be blank")
        return v.strip()


class InvestorCreate(InvestorBase):
    """
    Schema for ``POST /investors``.

    All base fields are required.
    """

    pass


class InvestorResponse(InvestorBase):
    """Schema returned by all investor endpoints."""

    id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

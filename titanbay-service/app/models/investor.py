"""
Investor domain model.

Represents an investor entity persisted in the ``investors`` table.
Supports three investor archetypes: Individual, Institution, Family Office.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, List

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.investment import Investment


class InvestorType(str, Enum):
    """Allowed investor classifications."""

    INDIVIDUAL = "Individual"
    INSTITUTION = "Institution"
    FAMILY_OFFICE = "Family Office"


class Investor(SQLModel, table=True):
    """
    SQLModel / SQLAlchemy table definition for investors.

    Constraints:
    - ``email`` has a unique index — duplicate registrations are rejected at DB level.
    - ``name`` is indexed for search & listing performance.
    """

    __tablename__ = "investors"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(index=True, max_length=255)
    investor_type: InvestorType
    email: str = Field(unique=True, index=True, max_length=320)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ── Relationships ──
    investments: List["Investment"] = Relationship(back_populates="investor")

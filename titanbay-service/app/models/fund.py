"""
Fund domain model.

Represents a private-market fund entity persisted in the ``funds`` table.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import CheckConstraint, DateTime
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.investment import Investment


class FundStatus(str, Enum):
    """Allowed lifecycle states for a Fund."""

    FUNDRAISING = "Fundraising"
    INVESTING = "Investing"
    CLOSED = "Closed"


class Fund(SQLModel, table=True):
    """
    SQLModel / SQLAlchemy table definition for funds.

    Business rules enforced at the DB level:
    - ``name`` is indexed for fast look-ups and listing.
    - ``target_size_usd`` uses DECIMAL(20,2) for precise currency arithmetic.
    - ``status`` defaults to *Fundraising* on creation.
    """

    __tablename__ = "funds"  # type: ignore[assignment]

    # ── DB-level CHECK constraints ──
    # Defence-in-depth: these enforce data integrity even if the Pydantic
    # validation layer is bypassed (e.g. direct SQL, admin scripts, seed data).
    # Note: ``status`` is NOT check-constrained here because SQLAlchemy creates
    # a native PostgreSQL ENUM type (``fundstatus``) which already rejects
    # invalid values at the DB level — a CHECK constraint would conflict.
    __table_args__ = (
        CheckConstraint("target_size_usd > 0", name="ck_funds_target_size_positive"),
        CheckConstraint("vintage_year >= 1900", name="ck_funds_vintage_year_min"),
        CheckConstraint("length(name) > 0", name="ck_funds_name_not_empty"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(index=True, max_length=255)
    vintage_year: int = Field(index=True)
    target_size_usd: Decimal = Field(max_digits=20, decimal_places=2)
    status: FundStatus = Field(default=FundStatus.FUNDRAISING)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
        index=True,  # enables efficient time-range queries (e.g. "funds created this quarter")
    )

    # ── Relationships ──
    investments: List["Investment"] = Relationship(back_populates="fund")

    def __repr__(self) -> str:
        return f"<Fund id={self.id} name='{self.name}' status={self.status.value}>"

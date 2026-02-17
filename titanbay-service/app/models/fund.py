"""
Fund domain model.

Represents a private-market fund entity persisted in the ``funds`` table.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime
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

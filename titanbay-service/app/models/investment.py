"""
Investment domain model.

Represents a single capital commitment from an investor into a fund.
Foreign keys to ``funds`` and ``investors`` enforce referential integrity at
the database level.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.fund import Fund
    from app.models.investor import Investor


class Investment(SQLModel, table=True):
    """
    SQLModel / SQLAlchemy table definition for investments.

    Design notes:
    - FK columns are indexed to speed up the frequent
      ``GET /funds/{fund_id}/investments`` query.
    - ``amount_usd`` uses DECIMAL(20,2) for cent-precise currency values.
    - No ``created_at`` column here — the spec models an explicit
      ``investment_date`` supplied by the caller.
    """

    __tablename__ = "investments"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    investor_id: uuid.UUID = Field(foreign_key="investors.id", index=True)
    fund_id: uuid.UUID = Field(foreign_key="funds.id", index=True)
    amount_usd: Decimal = Field(max_digits=20, decimal_places=2)
    investment_date: date

    # ── Relationships ──
    fund: Optional["Fund"] = Relationship(back_populates="investments")
    investor: Optional["Investor"] = Relationship(back_populates="investments")

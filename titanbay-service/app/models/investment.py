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

from sqlalchemy import CheckConstraint, Index
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.fund import Fund
    from app.models.investor import Investor


class Investment(SQLModel, table=True):
    """
    SQLModel / SQLAlchemy table definition for investments.

    Design notes:
    - FK columns are indexed individually for joins and existence checks.
    - A **composite index** ``ix_investments_fund_date`` covers the hottest
      query (``GET /funds/{fund_id}/investments``), enabling an index-only
      scan with correct sort order — no filesort required.
    - ``amount_usd`` uses DECIMAL(20,2) for cent-precise currency values.
    - No ``created_at`` column here — the spec models an explicit
      ``investment_date`` supplied by the caller.
    """

    __tablename__ = "investments"  # type: ignore[assignment]

    # ── Composite indexes & CHECK constraints ──
    # Covers: WHERE fund_id = ? ORDER BY investment_date DESC LIMIT ? OFFSET ?
    # PostgreSQL can satisfy this entirely via an index-only scan at scale.
    __table_args__ = (
        Index(
            "ix_investments_fund_date",
            "fund_id",
            "investment_date",  # B-tree default ASC; DESC scans are efficient via backward index scan
        ),
        CheckConstraint("amount_usd > 0", name="ck_investments_amount_positive"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    investor_id: uuid.UUID = Field(
        foreign_key="investors.id",
        index=True,
        ondelete="RESTRICT",  # Prevent deleting an investor that has investments
    )
    fund_id: uuid.UUID = Field(
        foreign_key="funds.id",
        index=True,
        ondelete="RESTRICT",  # Prevent deleting a fund that has investments
    )
    amount_usd: Decimal = Field(max_digits=20, decimal_places=2)
    investment_date: date

    # ── Relationships ──
    fund: Optional["Fund"] = Relationship(back_populates="investments")
    investor: Optional["Investor"] = Relationship(back_populates="investments")

    def __repr__(self) -> str:
        return (
            f"<Investment id={self.id} fund={self.fund_id} "
            f"investor={self.investor_id} amount=${self.amount_usd}>"
        )

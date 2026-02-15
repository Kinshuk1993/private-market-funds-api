"""
Seed script — populates the database with sample data for development / demo.

Usage (from the titanbay-service directory):
    docker-compose exec web python -m app.seed

Or run locally when the database is accessible:
    python -m app.seed

The script is idempotent: it checks for existing data before inserting.
"""

import asyncio
import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlmodel import SQLModel

from app.db.session import AsyncSessionLocal, engine
from app.models.fund import Fund, FundStatus
from app.models.investment import Investment
from app.models.investor import Investor, InvestorType

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

# ── Sample data matching the API spec examples ──

FUNDS = [
    Fund(
        id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
        name="Titanbay Growth Fund I",
        vintage_year=2024,
        target_size_usd=Decimal("250000000.00"),
        status=FundStatus.FUNDRAISING,
        created_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
    ),
    Fund(
        id=uuid.UUID("660e8400-e29b-41d4-a716-446655440001"),
        name="Titanbay Growth Fund II",
        vintage_year=2025,
        target_size_usd=Decimal("500000000.00"),
        status=FundStatus.FUNDRAISING,
        created_at=datetime(2024, 9, 22, 14, 20, 0, tzinfo=timezone.utc),
    ),
    Fund(
        id=uuid.UUID("110e8400-e29b-41d4-a716-446655440010"),
        name="Titanbay Buyout Fund III",
        vintage_year=2023,
        target_size_usd=Decimal("750000000.00"),
        status=FundStatus.INVESTING,
        created_at=datetime(2023, 6, 1, 8, 0, 0, tzinfo=timezone.utc),
    ),
    Fund(
        id=uuid.UUID("220e8400-e29b-41d4-a716-446655440020"),
        name="Titanbay Venture Fund I",
        vintage_year=2022,
        target_size_usd=Decimal("100000000.00"),
        status=FundStatus.CLOSED,
        created_at=datetime(2022, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
    ),
]

INVESTORS = [
    Investor(
        id=uuid.UUID("770e8400-e29b-41d4-a716-446655440002"),
        name="Goldman Sachs Asset Management",
        investor_type=InvestorType.INSTITUTION,
        email="investments@gsam.com",
        created_at=datetime(2024, 2, 10, 9, 15, 0, tzinfo=timezone.utc),
    ),
    Investor(
        id=uuid.UUID("880e8400-e29b-41d4-a716-446655440003"),
        name="CalPERS",
        investor_type=InvestorType.INSTITUTION,
        email="privateequity@calpers.ca.gov",
        created_at=datetime(2024, 9, 22, 15, 45, 0, tzinfo=timezone.utc),
    ),
    Investor(
        id=uuid.UUID("330e8400-e29b-41d4-a716-446655440030"),
        name="Smith Family Office",
        investor_type=InvestorType.FAMILY_OFFICE,
        email="invest@smithfo.com",
        created_at=datetime(2024, 4, 5, 11, 0, 0, tzinfo=timezone.utc),
    ),
    Investor(
        id=uuid.UUID("440e8400-e29b-41d4-a716-446655440040"),
        name="Jane Doe",
        investor_type=InvestorType.INDIVIDUAL,
        email="jane.doe@example.com",
        created_at=datetime(2024, 5, 20, 14, 30, 0, tzinfo=timezone.utc),
    ),
]

INVESTMENTS = [
    Investment(
        id=uuid.UUID("990e8400-e29b-41d4-a716-446655440004"),
        investor_id=uuid.UUID("770e8400-e29b-41d4-a716-446655440002"),
        fund_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
        amount_usd=Decimal("50000000.00"),
        investment_date=date(2024, 3, 15),
    ),
    Investment(
        id=uuid.UUID("aa0e8400-e29b-41d4-a716-446655440005"),
        investor_id=uuid.UUID("880e8400-e29b-41d4-a716-446655440003"),
        fund_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
        amount_usd=Decimal("75000000.00"),
        investment_date=date(2024, 9, 22),
    ),
    Investment(
        id=uuid.UUID("bb0e8400-e29b-41d4-a716-446655440006"),
        investor_id=uuid.UUID("330e8400-e29b-41d4-a716-446655440030"),
        fund_id=uuid.UUID("110e8400-e29b-41d4-a716-446655440010"),
        amount_usd=Decimal("25000000.00"),
        investment_date=date(2023, 8, 1),
    ),
    Investment(
        id=uuid.UUID("cc0e8400-e29b-41d4-a716-446655440007"),
        investor_id=uuid.UUID("440e8400-e29b-41d4-a716-446655440040"),
        fund_id=uuid.UUID("660e8400-e29b-41d4-a716-446655440001"),
        amount_usd=Decimal("5000000.00"),
        investment_date=date(2025, 1, 10),
    ),
]


async def seed() -> None:
    """Create tables and insert sample data if the database is empty."""
    # Ensure tables exist
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with AsyncSessionLocal() as session:
        # Check if data already exists (idempotent)
        result = await session.execute(select(Fund).limit(1))
        if result.scalars().first() is not None:
            logger.info("Database already contains data — skipping seed.")
            return

        for fund in FUNDS:
            session.add(fund)
        for investor in INVESTORS:
            session.add(investor)
        await session.commit()

        # Investments depend on funds & investors, so insert after
        for investment in INVESTMENTS:
            session.add(investment)
        await session.commit()

        logger.info(
            "Seeded %d funds, %d investors, %d investments",
            len(FUNDS),
            len(INVESTORS),
            len(INVESTMENTS),
        )


if __name__ == "__main__":
    asyncio.run(seed())

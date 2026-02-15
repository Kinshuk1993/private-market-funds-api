"""
Investor service — business logic layer for investor operations.

Handles duplicate-email detection before hitting the DB unique constraint,
providing a friendlier error message to the API consumer.

Race condition note:
    The pre-check ``get_by_email()`` followed by ``create()`` is subject to a
    TOCTOU (time-of-check / time-of-use) race: two concurrent requests with
    the same email could both pass the check.  The DB unique constraint is the
    true safety net.  We catch the resulting ``IntegrityError`` and translate
    it to a 409 Conflict so the client always gets a clean error message
    regardless of timing.
"""

import logging
from typing import List

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConflictException
from app.models.investor import Investor
from app.repositories.investor_repo import InvestorRepository
from app.schemas.investor import InvestorCreate

logger = logging.getLogger(__name__)


class InvestorService:
    """Encapsulates CRUD + business rules for :class:`Investor`."""

    def __init__(self, investor_repo: InvestorRepository):
        self._repo = investor_repo

    # ── Queries ──

    async def get_all_investors(
        self, skip: int = 0, limit: int = 100
    ) -> List[Investor]:
        """Return a paginated list of investors."""
        return await self._repo.get_all(skip=skip, limit=limit)

    # ── Commands ──

    async def create_investor(self, investor_in: InvestorCreate) -> Investor:
        """
        Create a new investor.

        Raises :class:`ConflictException` if an investor with the same
        email already exists.  The pre-check avoids an ugly DB constraint
        violation error reaching the client in the common case.

        A secondary ``IntegrityError`` catch handles the TOCTOU race where
        two concurrent requests slip past the pre-check simultaneously.
        """
        # Optimistic pre-check (fast path — catches 99.9% of duplicates)
        existing = await self._repo.get_by_email(str(investor_in.email))
        if existing:
            raise ConflictException(
                f"An investor with email '{investor_in.email}' already exists"
            )

        investor = Investor(**investor_in.model_dump())
        try:
            created = await self._repo.create(investor)
        except IntegrityError:
            # TOCTOU race: another request inserted the same email between
            # our check and our insert.  Roll back and return a clean 409.
            await self._repo.db.rollback()
            logger.warning(
                "IntegrityError caught for duplicate email '%s' (TOCTOU race)",
                investor_in.email,
            )
            raise ConflictException(
                f"An investor with email '{investor_in.email}' already exists"
            )

        logger.info("Created investor %s (%s)", created.id, created.name)
        return created

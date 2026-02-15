"""
Investor service — business logic layer for investor operations.

Handles duplicate-email detection before hitting the DB unique constraint,
providing a friendlier error message to the API consumer.
"""

import logging
from typing import List

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

    async def get_all_investors(self) -> List[Investor]:
        """Return all investors."""
        return await self._repo.get_all()

    # ── Commands ──

    async def create_investor(self, investor_in: InvestorCreate) -> Investor:
        """
        Create a new investor.

        Raises :class:`ConflictException` if an investor with the same
        email already exists.  This pre-check avoids an ugly DB constraint
        violation error reaching the client.
        """
        existing = await self._repo.get_by_email(str(investor_in.email))
        if existing:
            raise ConflictException(
                f"An investor with email '{investor_in.email}' already exists"
            )

        investor = Investor(**investor_in.model_dump())
        created = await self._repo.create(investor)
        logger.info("Created investor %s (%s)", created.id, created.name)
        return created

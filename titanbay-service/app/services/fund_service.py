"""
Fund service — business logic layer for fund operations.

All business rules and validation live here; the service never exposes
repository internals to the caller (encapsulation).

Raises domain-specific exceptions from ``app.core.exceptions`` so the
service layer stays framework-agnostic (no direct FastAPI imports).
"""

import logging
from typing import List
from uuid import UUID

from app.core.exceptions import NotFoundException
from app.models.fund import Fund
from app.repositories.fund_repo import FundRepository
from app.schemas.fund import FundCreate, FundUpdate

logger = logging.getLogger(__name__)


class FundService:
    """Encapsulates CRUD + business rules for :class:`Fund`."""

    def __init__(self, fund_repo: FundRepository):
        self._repo = fund_repo

    # ── Queries ──

    async def get_all_funds(self) -> List[Fund]:
        """Return all funds."""
        return await self._repo.get_all()

    async def get_fund(self, fund_id: UUID) -> Fund:
        """
        Retrieve a single fund by ID.

        Raises :class:`NotFoundException` if the fund does not exist.
        """
        fund = await self._repo.get(fund_id)
        if not fund:
            raise NotFoundException("Fund", fund_id)
        return fund

    # ── Commands ──

    async def create_fund(self, fund_in: FundCreate) -> Fund:
        """Create a new fund from validated input."""
        fund = Fund(**fund_in.model_dump())
        created = await self._repo.create(fund)
        logger.info("Created fund %s (%s)", created.id, created.name)
        return created

    async def update_fund(self, fund_update: FundUpdate) -> Fund:
        """
        Full replacement update of an existing fund.

        Per the API spec, the request body includes the ``id`` and all
        mutable fields.  This is a PUT semantic (full replace), not PATCH.

        Raises :class:`NotFoundException` if the fund does not exist.
        """
        fund = await self._repo.get(fund_update.id)
        if not fund:
            raise NotFoundException("Fund", fund_update.id)

        # Apply all fields from the update payload (excluding id, which is immutable)
        update_data = fund_update.model_dump(exclude={"id"})
        for key, value in update_data.items():
            setattr(fund, key, value)

        updated = await self._repo.update(fund)
        logger.info("Updated fund %s", updated.id)
        return updated

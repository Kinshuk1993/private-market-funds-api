"""
Investment repository — data-access layer for the ``investments`` table.

Extends generic CRUD with a fund-scoped query used by
``GET /funds/{fund_id}/investments``.
"""

from typing import List
from uuid import UUID

from sqlalchemy.future import select

from app.models.investment import Investment
from app.repositories.base import BaseRepository


class InvestmentRepository(BaseRepository[Investment]):
    """Concrete repository for :class:`Investment` entities."""

    async def get_by_fund(self, fund_id: UUID) -> List[Investment]:
        """
        Return all investments linked to a specific fund.

        The ``fund_id`` column is indexed, so this query performs an
        index seek rather than a full table scan.
        """
        stmt = select(self.model).where(self.model.fund_id == fund_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

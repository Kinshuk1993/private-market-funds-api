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

    async def get_by_fund(
        self, fund_id: UUID, skip: int = 0, limit: int = 100
    ) -> List[Investment]:
        """
        Return all investments linked to a specific fund, with pagination.

        The ``fund_id`` column is indexed, so this query performs an
        index seek rather than a full table scan.  Results are ordered
        by ``investment_date`` descending (most recent first) for a
        deterministic, user-friendly default.

        Parameters
        ----------
        fund_id : UUID
            The fund whose investments to retrieve.
        skip : int
            Number of rows to skip (offset).
        limit : int
            Maximum number of rows to return.
        """
        stmt = (
            select(self.model)
            .where(self.model.fund_id == fund_id)
            .order_by(self.model.investment_date.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

"""
Investor repository — data-access layer for the ``investors`` table.

Extends generic CRUD with an email look-up used during duplicate
detection in the service layer.
"""

from typing import Optional

from sqlalchemy.future import select

from app.models.investor import Investor
from app.repositories.base import BaseRepository


class InvestorRepository(BaseRepository[Investor]):
    """Concrete repository for :class:`Investor` entities."""

    async def get_by_email(self, email: str) -> Optional[Investor]:
        """
        Look up an investor by email address.

        Returns ``None`` if no investor with the given email exists.
        Used to enforce the uniqueness constraint *before* hitting the DB
        constraint, yielding a friendlier error message.
        """
        stmt = select(self.model).where(self.model.email == email)
        result = await self.db.execute(stmt)
        return result.scalars().first()

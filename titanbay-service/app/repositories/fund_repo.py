"""
Fund repository — data-access layer for the ``funds`` table.

Inherits generic CRUD from :class:`BaseRepository`.  No custom
query methods required for the current API spec.
"""

from app.models.fund import Fund
from app.repositories.base import BaseRepository


class FundRepository(BaseRepository[Fund]):
    """Concrete repository for :class:`Fund` entities."""

    pass

"""
Generic async repository (Data Access Layer).

Implements the Repository pattern on top of SQLAlchemy's ``AsyncSession``.
Concrete repositories inherit from ``BaseRepository[T]`` and can override
or extend any method when entity-specific query logic is needed.

Design rationale:
- Generic typing (``ModelType``) avoids duplicating CRUD logic per entity.
- All queries go through the session's unit-of-work, so callers get automatic
  transaction batching within a single request.
- ``get_all()`` enforces deterministic ordering (by primary key) to make
  paginated results stable — without this, PostgreSQL returns rows in
  heap-insertion order which can change between queries.
- **IntegrityError** is intentionally NOT caught here. Each service layer
  handles it differently (investor: 409 duplicate email, investment: 422
  FK race condition, fund: 422 constraint violation).  Re-raising lets
  the service decide the appropriate domain error.
- **OperationalError** (connection loss, deadlock) IS caught here and the
  session is rolled back + error re-raised, preventing dirty session leaks.
"""

import logging
from typing import Any, Generic, List, Optional, Type, TypeVar

from sqlalchemy import func
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlmodel import SQLModel

logger = logging.getLogger(__name__)

ModelType = TypeVar("ModelType", bound=SQLModel)


class BaseRepository(Generic[ModelType]):
    """
    Generic CRUD repository for SQLModel entities.

    Parameters
    ----------
    model : Type[ModelType]
        The SQLModel class this repository manages.
    db : AsyncSession
        An active async database session (injected per-request).
    """

    def __init__(self, model: Type[ModelType], db: AsyncSession):
        self.model = model
        self.db = db

    async def get(self, id: Any) -> Optional[ModelType]:
        """Fetch a single entity by primary key.  Returns ``None`` if not found."""
        return await self.db.get(self.model, id)

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[ModelType]:
        """
        Return a paginated list of entities.

        Results are ordered by primary key to ensure **deterministic pagination**.
        Without explicit ordering, PostgreSQL returns rows in heap order which
        can shift between queries, causing clients to see duplicate or missing
        records when paginating.

        Parameters
        ----------
        skip : int
            Number of rows to skip (offset).
        limit : int
            Maximum number of rows to return.
        """
        # Order by the first primary-key column for deterministic pagination
        pk_columns = self.model.__table__.primary_key.columns
        stmt = select(self.model).order_by(*pk_columns).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create(self, obj_in: ModelType) -> ModelType:
        """
        Insert a new entity and return the refreshed instance.

        **OperationalError** (connection loss, deadlock) triggers an automatic
        rollback to prevent the session from leaking a dirty transaction.
        **IntegrityError** is NOT caught — services handle it with domain-specific messages.
        """
        self.db.add(obj_in)
        try:
            await self.db.commit()
        except OperationalError:
            await self.db.rollback()
            logger.error("OperationalError during create for %s", self.model.__name__)
            raise
        await self.db.refresh(obj_in)
        return obj_in

    async def update(self, entity: ModelType) -> ModelType:
        """
        Persist changes to an already-tracked entity.

        The caller is responsible for mutating the entity's attributes
        before calling this method.  We merge, commit, then refresh to
        ensure the returned object reflects any DB-side defaults.
        """
        merged = await self.db.merge(entity)
        try:
            await self.db.commit()
        except OperationalError:
            await self.db.rollback()
            logger.error("OperationalError during update for %s", self.model.__name__)
            raise
        await self.db.refresh(merged)
        return merged

    async def count(self) -> int:
        """
        Return the total number of entities of this type.

        Useful for building pagination metadata (total pages, has_next, etc.)
        in list endpoints.
        """
        stmt = select(func.count()).select_from(self.model)
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def delete(self, id: Any) -> bool:
        """
        Delete an entity by primary key.

        Returns ``True`` if the entity was found and deleted, ``False`` if
        it did not exist.  Not currently exposed via the API but included
        for operational tooling and future endpoint expansion.
        """
        entity = await self.db.get(self.model, id)
        if entity is None:
            return False
        await self.db.delete(entity)
        try:
            await self.db.commit()
        except OperationalError:
            await self.db.rollback()
            logger.error(
                "OperationalError during delete for %s id=%s", self.model.__name__, id
            )
            raise
        return True

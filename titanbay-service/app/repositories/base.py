"""
Generic async repository (Data Access Layer).

Implements the Repository pattern on top of SQLAlchemy's ``AsyncSession``.
Concrete repositories inherit from ``BaseRepository[T]`` and can override
or extend any method when entity-specific query logic is needed.
"""

from typing import Any, Generic, List, Optional, Type, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlmodel import SQLModel

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
        Return a paginated list of entities ordered by primary key.

        Parameters
        ----------
        skip : int
            Number of rows to skip (offset).
        limit : int
            Maximum number of rows to return.
        """
        stmt = select(self.model).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create(self, obj_in: ModelType) -> ModelType:
        """Insert a new entity and return the refreshed instance."""
        self.db.add(obj_in)
        await self.db.commit()
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
        await self.db.commit()
        await self.db.refresh(merged)
        return merged

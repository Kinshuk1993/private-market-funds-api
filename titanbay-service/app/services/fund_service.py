"""
Fund service — business logic layer for fund operations.

All business rules and validation live here; the service never exposes
repository internals to the caller (encapsulation).

Raises domain-specific exceptions from ``app.core.exceptions`` so the
service layer stays framework-agnostic (no direct FastAPI imports).

Caching:
    Read operations (``get_all_funds``, ``get_fund``) check the in-memory
    TTL cache first.  Write operations (``create_fund``, ``update_fund``)
    invalidate all ``funds:`` cache keys so subsequent reads always return
    fresh data.
"""

import logging
from typing import List
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.core.cache import cache
from app.core.exceptions import BusinessRuleViolation, NotFoundException
from app.models.fund import Fund, FundStatus
from app.repositories.fund_repo import FundRepository
from app.schemas.fund import FundCreate, FundUpdate

logger = logging.getLogger(__name__)


class FundService:
    """Encapsulates CRUD + business rules for :class:`Fund`."""

    CACHE_PREFIX = "funds:"

    def __init__(self, fund_repo: FundRepository):
        self._repo = fund_repo

    # ── Queries ──

    async def get_all_funds(self, skip: int = 0, limit: int = 100) -> List[Fund]:
        """Return a paginated list of funds (cache-backed)."""
        cache_key = f"{self.CACHE_PREFIX}list:{skip}:{limit}"
        cached = cache.get(cache_key)
        if cached is not None:
            logger.debug("Cache hit for %s", cache_key)
            return cached

        funds = await self._repo.get_all(skip=skip, limit=limit)
        cache.set(cache_key, funds)
        return funds

    async def get_fund(self, fund_id: UUID) -> Fund:
        """
        Retrieve a single fund by ID (cache-backed).

        Raises :class:`NotFoundException` if the fund does not exist.
        """
        cache_key = f"{self.CACHE_PREFIX}{fund_id}"
        cached = cache.get(cache_key)
        if cached is not None:
            logger.debug("Cache hit for %s", cache_key)
            return cached

        fund = await self._repo.get(fund_id)
        if not fund:
            raise NotFoundException("Fund", fund_id)
        cache.set(cache_key, fund)
        return fund

    # ── Commands ──

    async def create_fund(self, fund_in: FundCreate) -> Fund:
        """
        Create a new fund from validated input.

        Catches ``IntegrityError`` from DB-level CHECK constraint violations
        (e.g. target_size_usd <= 0 bypassing Pydantic) and surfaces a clean 422.
        Invalidates fund cache after successful creation.
        """
        fund = Fund(**fund_in.model_dump())
        try:
            created = await self._repo.create(fund)
        except IntegrityError as exc:
            await self._repo.db.rollback()
            logger.warning("IntegrityError creating fund: %s", exc)
            raise BusinessRuleViolation(
                "Fund data violates a database constraint. Check all fields."
            )
        cache.invalidate(self.CACHE_PREFIX)
        logger.info("Created fund %s (%s)", created.id, created.name)
        return created

    async def update_fund(self, fund_update: FundUpdate) -> Fund:
        """
        Full replacement update of an existing fund.

        Per the API spec, the request body includes the ``id`` and all
        mutable fields.  This is a PUT semantic (full replace), not PATCH.

        Raises :class:`NotFoundException` if the fund does not exist.
        Raises :class:`BusinessRuleViolation` for invalid status transitions
        or DB constraint violations.
        Invalidates fund cache after successful update.
        """
        fund = await self._repo.get(fund_update.id)
        if not fund:
            raise NotFoundException("Fund", fund_update.id)

        # ── Status transition validation ──
        # Enforce a one-way lifecycle: Fundraising → Investing → Closed.
        # Re-opening a closed fund is never valid; going backwards is forbidden.
        _validate_status_transition(fund.status, fund_update.status)

        # Apply all fields from the update payload (excluding id, which is immutable)
        update_data = fund_update.model_dump(exclude={"id"})
        for key, value in update_data.items():
            setattr(fund, key, value)

        try:
            updated = await self._repo.update(fund)
        except IntegrityError as exc:
            await self._repo.db.rollback()
            logger.warning("IntegrityError updating fund %s: %s", fund_update.id, exc)
            raise BusinessRuleViolation(
                "Fund update violates a database constraint. Check all fields."
            )
        cache.invalidate(self.CACHE_PREFIX)
        logger.info("Updated fund %s", updated.id)
        return updated


# ── Status transition rules ──

# Allowed transitions: only forward movement through the lifecycle.
_ALLOWED_TRANSITIONS: dict[FundStatus, set[FundStatus]] = {
    FundStatus.FUNDRAISING: {
        FundStatus.FUNDRAISING,
        FundStatus.INVESTING,
        FundStatus.CLOSED,
    },
    FundStatus.INVESTING: {FundStatus.INVESTING, FundStatus.CLOSED},
    FundStatus.CLOSED: {FundStatus.CLOSED},  # terminal state — no going back
}


def _validate_status_transition(current: FundStatus, requested: FundStatus) -> None:
    """
    Enforce one-way fund lifecycle transitions.

    Fundraising → Investing → Closed.  Moving backwards (e.g. Closed → Fundraising)
    raises a :class:`BusinessRuleViolation`.
    """
    if requested not in _ALLOWED_TRANSITIONS.get(current, set()):
        raise BusinessRuleViolation(
            f"Invalid status transition: '{current.value}' → '{requested.value}'. "
            f"Fund lifecycle is Fundraising → Investing → Closed (one-way)."
        )

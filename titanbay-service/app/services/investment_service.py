"""
Investment service — business logic layer for investment (commitment) operations.

Contains the most critical business rule in the system: investments into
*Closed* funds must be rejected.

Caching:
    Read operations (``get_investments_by_fund``) check the in-memory TTL
    cache first.  Write operations (``create_investment``) invalidate all
    ``investments:`` cache keys.
"""

import logging
from typing import List
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.core.cache import cache
from app.core.exceptions import BusinessRuleViolation, NotFoundException
from app.models.fund import FundStatus
from app.models.investment import Investment
from app.repositories.fund_repo import FundRepository
from app.repositories.investment_repo import InvestmentRepository
from app.repositories.investor_repo import InvestorRepository
from app.schemas.investment import InvestmentCreate

logger = logging.getLogger(__name__)


class InvestmentService:
    """
    Encapsulates CRUD + business rules for :class:`Investment`.

    Requires both fund and investor repositories because creating an
    investment must validate the existence and state of both related entities.
    """

    CACHE_PREFIX = "investments:"

    def __init__(
        self,
        invest_repo: InvestmentRepository,
        fund_repo: FundRepository,
        investor_repo: InvestorRepository,
    ):
        self._invest_repo = invest_repo
        self._fund_repo = fund_repo
        self._investor_repo = investor_repo

    # ── Queries ──

    async def get_investments_by_fund(
        self, fund_id: UUID, skip: int = 0, limit: int = 100
    ) -> List[Investment]:
        """
        Return investments for a given fund, with pagination (cache-backed).

        The fund is validated first so the caller gets a clear 404 instead
        of an empty list when the fund does not exist.
        """
        fund = await self._fund_repo.get(fund_id)
        if not fund:
            raise NotFoundException("Fund", fund_id)

        cache_key = f"{self.CACHE_PREFIX}{fund_id}:{skip}:{limit}"
        cached = cache.get(cache_key)
        if cached is not None:
            logger.debug("Cache hit for %s", cache_key)
            return cached

        investments = await self._invest_repo.get_by_fund(fund_id, skip=skip, limit=limit)
        cache.set(cache_key, investments)
        return investments

    # ── Commands ──

    async def create_investment(
        self, fund_id: UUID, invest_in: InvestmentCreate
    ) -> Investment:
        """
        Record a new investment (capital commitment) into a fund.

        Validation sequence:
        1. The referenced **fund** must exist → 404 if not.
        2. The fund must **not** be in ``Closed`` status → 422 if it is.
           This is the key business invariant: closed funds accept no new capital.
        3. The referenced **investor** must exist → 404 if not.
           Without this check we would get an opaque FK-violation from Postgres.

        Only after all preconditions pass is the investment persisted.
        Invalidates investment cache after successful creation.
        """
        # 1 ─ Validate fund existence
        fund = await self._fund_repo.get(fund_id)
        if not fund:
            raise NotFoundException("Fund", fund_id)

        # 2 ─ Business rule: closed funds reject new investments
        if fund.status == FundStatus.CLOSED:
            raise BusinessRuleViolation(
                f"Fund '{fund.name}' is closed and no longer accepts investments"
            )

        # 3 ─ Validate investor existence
        investor = await self._investor_repo.get(invest_in.investor_id)
        if not investor:
            raise NotFoundException("Investor", invest_in.investor_id)

        # 4 ─ Persist
        # IntegrityError catch handles TOCTOU races: if the fund or investor
        # was deleted between our existence check and the INSERT, PostgreSQL's
        # FK constraint fires and we translate it to a meaningful error.
        investment = Investment(
            fund_id=fund_id,
            investor_id=invest_in.investor_id,
            amount_usd=invest_in.amount_usd,
            investment_date=invest_in.investment_date,
        )
        try:
            created = await self._invest_repo.create(investment)
        except IntegrityError as exc:
            await self._invest_repo.db.rollback()
            logger.warning(
                "IntegrityError creating investment (fund=%s, investor=%s): %s",
                fund_id,
                invest_in.investor_id,
                exc,
            )
            raise BusinessRuleViolation(
                "Investment could not be created — a referenced fund or investor "
                "may have been removed, or a database constraint was violated."
            )
        cache.invalidate(self.CACHE_PREFIX)
        logger.info(
            "Created investment %s: investor %s → fund %s ($%s)",
            created.id,
            created.investor_id,
            created.fund_id,
            created.amount_usd,
        )
        return created

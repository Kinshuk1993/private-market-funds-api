"""
Investment API endpoints.

Investments are scoped under funds:
- GET   /funds/{fund_id}/investments  — List investments for a fund
- POST  /funds/{fund_id}/investments  — Create a new investment in a fund
"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.fund import Fund
from app.models.investment import Investment
from app.models.investor import Investor
from app.repositories.fund_repo import FundRepository
from app.repositories.investment_repo import InvestmentRepository
from app.repositories.investor_repo import InvestorRepository
from app.schemas.common import ErrorResponse, ValidationErrorResponse
from app.schemas.investment import InvestmentCreate, InvestmentResponse
from app.services.investment_service import InvestmentService

router = APIRouter()


# ── Dependency injection ──


def _get_investment_service(db: AsyncSession = Depends(get_db)) -> InvestmentService:
    """
    Build an InvestmentService wired to the current request's DB session.

    The service requires all three repositories because creating an
    investment validates both the fund and the investor.
    """
    return InvestmentService(
        invest_repo=InvestmentRepository(Investment, db),
        fund_repo=FundRepository(Fund, db),
        investor_repo=InvestorRepository(Investor, db),
    )


# ── Endpoints ──
# NOTE: Full path is specified here because the router is mounted at the
# API-version root (not under /funds) to keep route definitions explicit.


@router.get(
    "/funds/{fund_id}/investments",
    response_model=List[InvestmentResponse],
    summary="List investments for a fund",
    description=(
        "Returns all investment commitments associated with the given fund. "
        "Use ``skip`` and ``limit`` to paginate."
    ),
    responses={
        404: {"model": ErrorResponse, "description": "Fund not found"},
    },
)
async def list_investments(
    fund_id: UUID,
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Max records to return"),
    service: InvestmentService = Depends(_get_investment_service),
) -> List[InvestmentResponse]:
    return await service.get_investments_by_fund(fund_id, skip=skip, limit=limit)


@router.post(
    "/funds/{fund_id}/investments",
    response_model=InvestmentResponse,
    status_code=201,
    summary="Create a new investment",
    description=(
        "Records a capital commitment from an investor into a fund. "
        "The fund must not be in *Closed* status, and both the fund and "
        "the investor must exist."
    ),
    responses={
        404: {"model": ErrorResponse, "description": "Fund or investor not found"},
        422: {
            "model": ValidationErrorResponse,
            "description": "Validation error or business rule violation",
        },
    },
)
async def create_investment(
    fund_id: UUID,
    investment: InvestmentCreate,
    service: InvestmentService = Depends(_get_investment_service),
) -> InvestmentResponse:
    return await service.create_investment(fund_id, investment)

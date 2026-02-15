"""
Investor API endpoints.

- GET   /investors  — List all investors
- POST  /investors  — Create a new investor
"""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.investor import Investor
from app.repositories.investor_repo import InvestorRepository
from app.schemas.investor import InvestorCreate, InvestorResponse
from app.services.investor_service import InvestorService

router = APIRouter()


# ── Dependency injection ──


def _get_investor_service(db: AsyncSession = Depends(get_db)) -> InvestorService:
    """Build an InvestorService wired to the current request's DB session."""
    return InvestorService(InvestorRepository(Investor, db))


# ── Endpoints ──


@router.get(
    "/",
    response_model=List[InvestorResponse],
    summary="List all investors",
    description="Returns every investor in the system.",
)
async def list_investors(
    service: InvestorService = Depends(_get_investor_service),
) -> List[InvestorResponse]:
    return await service.get_all_investors()


@router.post(
    "/",
    response_model=InvestorResponse,
    status_code=201,
    summary="Create a new investor",
    description=(
        "Registers a new investor.  The email must be unique; a 409 Conflict "
        "is returned if the email is already in use."
    ),
)
async def create_investor(
    investor: InvestorCreate,
    service: InvestorService = Depends(_get_investor_service),
) -> InvestorResponse:
    return await service.create_investor(investor)

"""
Fund API endpoints.

All four fund-related routes from the API specification:
- GET    /funds          — List all funds
- POST   /funds          — Create a new fund
- PUT    /funds          — Update an existing fund  (id in request body)
- GET    /funds/{id}     — Retrieve a specific fund
"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.fund import Fund
from app.repositories.fund_repo import FundRepository
from app.schemas.common import ErrorResponse, ValidationErrorResponse
from app.schemas.fund import FundCreate, FundResponse, FundUpdate
from app.services.fund_service import FundService

router = APIRouter()


# ── Dependency injection ──
# FastAPI's Depends() system creates a fresh service instance per request,
# each wired to its own DB session.  This ensures one request's transaction
# cannot bleed into another and makes unit testing easy (swap the dependency).


def _get_fund_service(db: AsyncSession = Depends(get_db)) -> FundService:
    """Build a FundService wired to the current request's DB session."""
    return FundService(FundRepository(Fund, db))


# ── Endpoints ──


@router.get(
    "",
    response_model=List[FundResponse],
    summary="List all funds",
    description=(
        "Returns a paginated list of funds.  Use ``skip`` and ``limit`` "
        "query parameters to page through large result sets."
    ),
)
async def list_funds(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Max records to return"),
    service: FundService = Depends(_get_fund_service),
) -> List[FundResponse]:
    return await service.get_all_funds(skip=skip, limit=limit)


@router.post(
    "",
    response_model=FundResponse,
    status_code=201,
    summary="Create a new fund",
    description="Accepts fund details and creates a new fund record.",
    responses={
        422: {"model": ValidationErrorResponse, "description": "Validation error"},
    },
)
async def create_fund(
    fund: FundCreate,
    service: FundService = Depends(_get_fund_service),
) -> FundResponse:
    return await service.create_fund(fund)


@router.put(
    "",
    response_model=FundResponse,
    summary="Update an existing fund",
    description=(
        "Full replacement update.  The request body must include the fund ``id`` "
        "along with all fields.  Per the API spec, the id is passed in the body "
        "rather than the URL path."
    ),
    responses={
        404: {"model": ErrorResponse, "description": "Fund not found"},
        422: {"model": ValidationErrorResponse, "description": "Validation error"},
    },
)
async def update_fund(
    fund_update: FundUpdate,
    service: FundService = Depends(_get_fund_service),
) -> FundResponse:
    return await service.update_fund(fund_update)


@router.get(
    "/{fund_id}",
    response_model=FundResponse,
    summary="Get a specific fund",
    description="Retrieve a single fund by its UUID.",
    responses={
        404: {"model": ErrorResponse, "description": "Fund not found"},
    },
)
async def get_fund(
    fund_id: UUID,
    service: FundService = Depends(_get_fund_service),
) -> FundResponse:
    return await service.get_fund(fund_id)

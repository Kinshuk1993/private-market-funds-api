#!/bin/bash

cd titanbay-service

echo "----------------------------------------"
echo "1. Creating 'app/services/investment_service.py'"
echo "----------------------------------------"
# This service now owns the logic for Investments, including validating the Fund status.
# It depends on FundRepository (to check status) and InvestmentRepository (to save).

cat <<EOF > app/services/investment_service.py
from uuid import UUID
from fastapi import HTTPException
from app.repositories.fund_repo import FundRepository
from app.repositories.investment_repo import InvestmentRepository
from app.schemas.investment import InvestmentCreate
from app.models.fund import FundStatus
from app.models.investment import Investment

class InvestmentService:
    def __init__(self, invest_repo: InvestmentRepository, fund_repo: FundRepository):
        self.invest_repo = invest_repo
        self.fund_repo = fund_repo

    async def create_investment(self, fund_id: UUID, invest_in: InvestmentCreate) -> Investment:
        # 1. Validate Fund Exists
        fund = await self.fund_repo.get(fund_id)
        if not fund:
            raise HTTPException(status_code=404, detail="Fund not found")

        # 2. Business Rule: Cannot invest in Closed funds
        if fund.status == FundStatus.CLOSED:
            raise HTTPException(status_code=400, detail="Fund is closed to new investments")

        # 3. Create Investment
        investment = Investment(
            fund_id=fund_id,
            investor_id=invest_in.investor_id,
            amount_usd=invest_in.amount_usd,
            investment_date=invest_in.investment_date
        )
        return await self.invest_repo.create(investment)

    async def get_investments_by_fund(self, fund_id: UUID):
        # We verify the fund exists first, just to be clean
        fund = await self.fund_repo.get(fund_id)
        if not fund:
            raise HTTPException(status_code=404, detail="Fund not found")
            
        return await self.invest_repo.get_by_fund(fund_id)
EOF

echo "----------------------------------------"
echo "2. Cleaning up 'app/services/fund_service.py'"
echo "----------------------------------------"
# FundService now ONLY cares about Funds. No more Investment logic here.

cat <<EOF > app/services/fund_service.py
from uuid import UUID
from fastapi import HTTPException
from app.repositories.fund_repo import FundRepository
from app.schemas.fund import FundCreate, FundUpdate
from app.models.fund import Fund

class FundService:
    def __init__(self, fund_repo: FundRepository):
        self.fund_repo = fund_repo

    async def create_fund(self, fund_in: FundCreate) -> Fund:
        fund = Fund(**fund_in.model_dump())
        return await self.fund_repo.create(fund)

    async def update_fund(self, fund_id: UUID, fund_update: FundUpdate) -> Fund:
        fund = await self.fund_repo.get(fund_id)
        if not fund:
            raise HTTPException(status_code=404, detail="Fund not found")
        
        update_data = fund_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(fund, key, value)

        return await self.fund_repo.create(fund)
EOF

echo "----------------------------------------"
echo "3. Creating 'app/api/v1/endpoints/investments.py'"
echo "----------------------------------------"
# New Controller specifically for Investment endpoints

cat <<EOF > app/api/v1/endpoints/investments.py
from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.schemas.investment import InvestmentCreate, InvestmentResponse
from app.services.investment_service import InvestmentService
from app.repositories.fund_repo import FundRepository
from app.repositories.investment_repo import InvestmentRepository
from app.models.fund import Fund
from app.models.investment import Investment

router = APIRouter()

def get_investment_service(db: AsyncSession = Depends(get_db)) -> InvestmentService:
    return InvestmentService(
        InvestmentRepository(Investment, db),
        FundRepository(Fund, db)
    )

# Note: We include the full path here so we can mount it cleanly in API.py
# This handles: POST /funds/{fund_id}/investments
@router.post("/funds/{fund_id}/investments", response_model=InvestmentResponse, status_code=201)
async def create_investment(
    fund_id: UUID,
    investment: InvestmentCreate,
    service: InvestmentService = Depends(get_investment_service)
):
    return await service.create_investment(fund_id, investment)

# This handles: GET /funds/{fund_id}/investments
@router.get("/funds/{fund_id}/investments", response_model=List[InvestmentResponse])
async def list_investments(
    fund_id: UUID,
    service: InvestmentService = Depends(get_investment_service)
):
    return await service.get_investments_by_fund(fund_id)
EOF

echo "----------------------------------------"
echo "4. Cleaning up 'app/api/v1/endpoints/funds.py'"
echo "----------------------------------------"
# Removing Investment routes from here.

cat <<EOF > app/api/v1/endpoints/funds.py
from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.schemas.fund import FundCreate, FundResponse, FundUpdate
from app.services.fund_service import FundService
from app.repositories.fund_repo import FundRepository
from app.models.fund import Fund

router = APIRouter()

def get_fund_service(db: AsyncSession = Depends(get_db)) -> FundService:
    return FundService(FundRepository(Fund, db))

@router.get("/", response_model=List[FundResponse])
async def list_funds(service: FundService = Depends(get_fund_service)):
    return await service.fund_repo.get_all()

@router.post("/", response_model=FundResponse, status_code=201)
async def create_fund(
    fund: FundCreate, 
    service: FundService = Depends(get_fund_service)
):
    return await service.create_fund(fund)

@router.put("/{fund_id}", response_model=FundResponse)
async def update_fund(
    fund_id: UUID,
    fund_update: FundUpdate,
    service: FundService = Depends(get_fund_service)
):
    return await service.update_fund(fund_id, fund_update)

@router.get("/{fund_id}", response_model=FundResponse)
async def get_fund(
    fund_id: UUID,
    service: FundService = Depends(get_fund_service)
):
    fund = await service.fund_repo.get(fund_id)
    if not fund:
        raise HTTPException(status_code=404, detail="Fund not found")
    return fund
EOF

echo "----------------------------------------"
echo "5. Updating 'app/api/v1/api.py'"
echo "----------------------------------------"
# Register the new Investments router.
# Notice we don't add a prefix for investments because the routes define "/funds/{id}/..." themselves.

cat <<EOF > app/api/v1/api.py
from fastapi import APIRouter
from app.api.v1.endpoints import funds, investors, investments

api_router = APIRouter()

api_router.include_router(funds.router, prefix="/funds", tags=["Funds"])
api_router.include_router(investors.router, prefix="/investors", tags=["Investors"])
# Investments router already contains the path /funds/{id}/investments
api_router.include_router(investments.router, tags=["Investments"])
EOF

echo "Refactor Complete! Services and Controllers are now decoupled."
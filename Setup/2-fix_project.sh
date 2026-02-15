#!/bin/bash

# Navigate to the project folder
cd titanbay-service

echo "----------------------------------------"
echo "Fixing Missing Schemas (Investors)"
echo "----------------------------------------"

cat <<EOF > app/schemas/investor.py
from pydantic import BaseModel, EmailStr, ConfigDict
from uuid import UUID
from datetime import datetime
from app.models.investor import InvestorType

class InvestorBase(BaseModel):
    name: str
    investor_type: InvestorType
    email: EmailStr

class InvestorCreate(InvestorBase):
    pass

class InvestorResponse(InvestorBase):
    id: UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
EOF

echo "----------------------------------------"
echo "Fixing Missing Repositories (Investors)"
echo "----------------------------------------"

cat <<EOF > app/repositories/investor_repo.py
from app.repositories.base import BaseRepository
from app.models.investor import Investor

class InvestorRepository(BaseRepository[Investor]):
    pass
EOF

echo "----------------------------------------"
echo "Fixing Missing Services (Investors)"
echo "----------------------------------------"

cat <<EOF > app/services/investor_service.py
from app.repositories.investor_repo import InvestorRepository
from app.schemas.investor import InvestorCreate
from app.models.investor import Investor

class InvestorService:
    def __init__(self, investor_repo: InvestorRepository):
        self.investor_repo = investor_repo

    async def create_investor(self, investor_in: InvestorCreate) -> Investor:
        investor = Investor(**investor_in.model_dump())
        return await self.investor_repo.create(investor)
    
    async def get_all_investors(self):
        return await self.investor_repo.get_all()
EOF

echo "----------------------------------------"
echo "Fixing Missing Endpoints (Investors.py)"
echo "----------------------------------------"

cat <<EOF > app/api/v1/endpoints/investors.py
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.schemas.investor import InvestorCreate, InvestorResponse
from app.services.investor_service import InvestorService
from app.repositories.investor_repo import InvestorRepository
from app.models.investor import Investor

router = APIRouter()

def get_investor_service(db: AsyncSession = Depends(get_db)) -> InvestorService:
    return InvestorService(InvestorRepository(Investor, db))

@router.get("/", response_model=List[InvestorResponse])
async def list_investors(service: InvestorService = Depends(get_investor_service)):
    return await service.get_all_investors()

@router.post("/", response_model=InvestorResponse, status_code=201)
async def create_investor(
    investor: InvestorCreate, 
    service: InvestorService = Depends(get_investor_service)
):
    return await service.create_investor(investor)
EOF

echo "----------------------------------------"
echo "Updating Funds Logic (Adding PUT Support)"
echo "----------------------------------------"

# 1. Update Fund Service to handle updates
cat <<EOF > app/services/fund_service.py
from uuid import UUID
from fastapi import HTTPException
from app.repositories.fund_repo import FundRepository
from app.repositories.investment_repo import InvestmentRepository
from app.schemas.fund import FundCreate, FundUpdate
from app.schemas.investment import InvestmentCreate
from app.models.fund import Fund, FundStatus
from app.models.investment import Investment

class FundService:
    def __init__(self, fund_repo: FundRepository, invest_repo: InvestmentRepository):
        self.fund_repo = fund_repo
        self.invest_repo = invest_repo

    async def create_fund(self, fund_in: FundCreate) -> Fund:
        fund = Fund(**fund_in.model_dump())
        return await self.fund_repo.create(fund)

    async def update_fund(self, fund_id: UUID, fund_update: FundUpdate) -> Fund:
        # 1. Get existing fund
        fund = await self.fund_repo.get(fund_id)
        if not fund:
            raise HTTPException(status_code=404, detail="Fund not found")
        
        # 2. Update fields if provided
        update_data = fund_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(fund, key, value)

        # 3. Save
        return await self.fund_repo.create(fund) 

    async def add_investment(self, fund_id: UUID, invest_in: InvestmentCreate) -> Investment:
        fund = await self.fund_repo.get(fund_id)
        if not fund:
            raise HTTPException(status_code=404, detail="Fund not found")

        if fund.status == FundStatus.CLOSED:
            raise HTTPException(status_code=400, detail="Fund is closed to new investments")

        investment = Investment(
            fund_id=fund_id,
            investor_id=invest_in.investor_id,
            amount_usd=invest_in.amount_usd,
            investment_date=invest_in.investment_date
        )
        return await self.invest_repo.create(investment)
EOF

# 2. Update Fund Router to include PUT
cat <<EOF > app/api/v1/endpoints/funds.py
from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.schemas.fund import FundCreate, FundResponse, FundUpdate
from app.schemas.investment import InvestmentCreate, InvestmentResponse
from app.services.fund_service import FundService
from app.repositories.fund_repo import FundRepository
from app.repositories.investment_repo import InvestmentRepository
from app.models.fund import Fund
from app.models.investment import Investment

router = APIRouter()

def get_fund_service(db: AsyncSession = Depends(get_db)) -> FundService:
    return FundService(
        FundRepository(Fund, db),
        InvestmentRepository(Investment, db)
    )

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

# --- Nested Investment Endpoints ---
@router.post("/{fund_id}/investments", response_model=InvestmentResponse, status_code=201)
async def create_investment(
    fund_id: UUID,
    investment: InvestmentCreate,
    service: FundService = Depends(get_fund_service)
):
    return await service.add_investment(fund_id, investment)

@router.get("/{fund_id}/investments", response_model=List[InvestmentResponse])
async def list_investments(
    fund_id: UUID,
    service: FundService = Depends(get_fund_service)
):
    return await service.invest_repo.get_by_fund(fund_id)
EOF

echo "----------------------------------------"
echo "Registering New Router in Main.py"
echo "----------------------------------------"

cat <<EOF > app/main.py
from fastapi import FastAPI
from sqlmodel import SQLModel
from app.db.session import engine
from app.api.v1.endpoints import funds, investors

app = FastAPI(
    title="Titanbay Private Markets API",
    version="1.0.0",
    description="Senior Level Clean Architecture Implementation"
)

# Startup event to create tables (For simplicity in this task. In prod, use Alembic)
@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        import app.models.fund
        import app.models.investor
        import app.models.investment
        await conn.run_sync(SQLModel.metadata.create_all)

# Register Routers
app.include_router(funds.router, prefix="/api/v1/funds", tags=["Funds"])
app.include_router(investors.router, prefix="/api/v1/investors", tags=["Investors"])

@app.get("/health")
def health_check():
    return {"status": "ok"}
EOF

echo "Fix complete. Please run 'docker-compose up --build' to apply changes."
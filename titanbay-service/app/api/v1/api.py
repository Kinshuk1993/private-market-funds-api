"""
V1 API router aggregation.

All versioned endpoint routers are mounted here under a common prefix.
The top-level ``main.py`` mounts this router at ``/api/v1``.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import funds, investors, investments

api_router = APIRouter()

api_router.include_router(funds.router, prefix="/funds", tags=["Funds"])
api_router.include_router(investors.router, prefix="/investors", tags=["Investors"])

# Investments router defines its own full paths (/funds/{fund_id}/investments)
# so it is mounted at the root of the v1 prefix without an additional prefix.
api_router.include_router(investments.router, tags=["Investments"])

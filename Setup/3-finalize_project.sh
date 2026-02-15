#!/bin/bash

cd titanbay-service

echo "----------------------------------------"
echo "1. Creating 'app/api/v1/api.py' (Router Aggregator)"
echo "----------------------------------------"

# This keeps main.py clean by grouping all V1 routes here
cat <<EOF > app/api/v1/api.py
from fastapi import APIRouter
from app.api.v1.endpoints import funds, investors

api_router = APIRouter()

api_router.include_router(funds.router, prefix="/funds", tags=["Funds"])
api_router.include_router(investors.router, prefix="/investors", tags=["Investors"])
EOF

echo "----------------------------------------"
echo "2. Creating 'app/core/exceptions.py' (Global Error Handling)"
echo "----------------------------------------"

# This catches unhandled errors so the API doesn't just crash silently
cat <<EOF > app/core/exceptions.py
from fastapi import Request, FastAPI
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

def add_exception_handlers(app: FastAPI):
    
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": True, "message": exc.detail},
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        # In a real app, you would log the error to Sentry/Datadog here
        print(f"Global Error: {exc}")
        return JSONResponse(
            status_code=500,
            content={"error": True, "message": "Internal Server Error. Please contact support."},
        )
EOF

echo "----------------------------------------"
echo "3. Updating 'app/main.py' to wire everything together"
echo "----------------------------------------"

# Now main.py is super clean - just setup and imports
cat <<EOF > app/main.py
from fastapi import FastAPI
from sqlmodel import SQLModel
from app.db.session import engine
from app.api.v1.api import api_router
from app.core.config import settings
from app.core.exceptions import add_exception_handlers

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="Senior Level Clean Architecture Implementation",
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# 1. Add Global Error Handlers
add_exception_handlers(app)

# 2. Register all V1 Routers (Funds + Investors)
app.include_router(api_router, prefix=settings.API_V1_STR)

# 3. Startup Event (Create DB Tables)
@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        import app.models.fund
        import app.models.investor
        import app.models.investment
        await conn.run_sync(SQLModel.metadata.create_all)

@app.get("/health")
def health_check():
    return {"status": "ok", "version": "1.0.0"}
EOF

echo "----------------------------------------"
echo "Done! Project structure is now 100% complete."
echo "----------------------------------------"
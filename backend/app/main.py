import sys
import asyncio

if sys.platform == 'win32':
    # Asyncio on Windows 3.13 requires Selector loop for some DB drivers
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI

from contextlib import asynccontextmanager
from backend.app.database import engine, Base
from backend.app.api.v1.endpoints.webhooks import router as webhooks_router
from backend.app.api.v1.endpoints.volunteers import router as volunteers_router
from backend.app.api.v1.endpoints.needs import router as needs_router
from backend.app.api.v1.endpoints.dispatches import router as dispatches_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup (For development/MVP setup)
    # In production, we'd use Alembic. For V1.0 baseline, this works.
    try:
        from sqlalchemy import text
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
            await conn.run_sync(Base.metadata.create_all)
        print("[Lifespan] Database tables created/verified successfully.")

    except Exception as e:
        print(f"[Lifespan WARNING] Database connection or creation failed: {e}")
        print("[Lifespan WARNING] Continuing boot for endpoint route verification purposes.")
    yield


app = FastAPI(
    title="Sahyog Setu API",
    description="Smart allocation operating system for NGO logistics",
    version="1.0.0",
    lifespan=lifespan
)

# Include Routers
app.include_router(webhooks_router, prefix="/api/v1/webhooks", tags=["webhooks"])
app.include_router(volunteers_router, prefix="/api/v1/volunteers", tags=["volunteers"])
app.include_router(needs_router, prefix="/api/v1/needs", tags=["needs"])
app.include_router(dispatches_router, prefix="/api/v1/dispatches", tags=["dispatches"])

@app.get("/")
async def root():
    return {
        "status": "healthy", 
        "version": "1.0.0", 
        "message": "Welcome to Sahyog Setu API",
        "docs_url": "/docs"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "1.0.0"}

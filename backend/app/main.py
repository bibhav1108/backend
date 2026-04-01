import sys
import asyncio

if sys.platform == 'win32':
    # Asyncio on Windows 3.13 requires Selector loop for some DB drivers
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.config import settings

from contextlib import asynccontextmanager
from sqlalchemy import text
from backend.app.database import engine, Base
from backend.app.api.v1.endpoints.webhooks import router as webhooks_router
from backend.app.api.v1.endpoints.volunteers import router as volunteers_router
from backend.app.api.v1.endpoints.marketplace import router as marketplace_router
from backend.app.api.v1.endpoints.marketplace_dispatches import router as m_dispatches_router
from backend.app.services.telegram_service import telegram_service
from backend.app.api.v1.endpoints.auth import router as auth_router
from backend.app.api.v1.endpoints.inventory import router as inventory_router
from backend.app.api.v1.endpoints.organizations import router as organizations_router
from backend.app.api.v1.endpoints.users import router as users_router
from backend.app.api.v1.endpoints.meta import router as meta_router
from backend.app.api.v1.endpoints.campaigns import router as campaigns_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Lightweight startup
    try:
        # 1. Database Connectivity Check (Non-blocking search)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        print("[Lifespan] Database connection verified.")

        # 2. Sync Telegram Bot Commands (Quick API call)
        await telegram_service.set_bot_commands()
        print("[Lifespan] Telegram service configured.")
    except Exception as e:
        print(f"[Lifespan WARNING] Non-critical startup task failed: {e}")
    
    yield
    
    # Graceful Shutdown
    await telegram_service.close()
    print("[Lifespan] Telegram service client closed.")


app = FastAPI(
    title="SahyogSync API",
    description="Smart allocation operating system for NGO logistics",
    lifespan=lifespan
)

# CORS Middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(organizations_router, prefix="/api/v1/organizations", tags=["organizations"])
app.include_router(users_router, prefix="/api/v1/users", tags=["users"])
app.include_router(meta_router, prefix="/api/v1", tags=["metadata"])
app.include_router(webhooks_router, prefix="/api/v1/webhooks", tags=["webhooks"])
app.include_router(volunteers_router, prefix="/api/v1/volunteers", tags=["volunteers"])
app.include_router(marketplace_router, prefix="/api/v1/marketplace/needs", tags=["marketplace"])
app.include_router(marketplace_router, prefix="/api/v1/needs", tags=["marketplace-legacy"]) # Compatibility
app.include_router(m_dispatches_router, prefix="/api/v1/marketplace/dispatches", tags=["marketplace"])
app.include_router(inventory_router, prefix="/api/v1/inventory", tags=["inventory"])
app.include_router(campaigns_router, prefix="/api/v1/campaigns", tags=["campaigns"])

@app.get("/")
async def root():
    return {
        "status": "healthy", 
        "version": "2.0.0", 
        "message": "Welcome to SahyogSync", 
        "docs_url": "/docs"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "2.0.0"}

import sys
import asyncio

if sys.platform == 'win32':
    # Asyncio on Windows 3.13 requires Selector loop for some DB drivers
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
from backend.app.config import settings

from contextlib import asynccontextmanager
from sqlalchemy import text, delete
from datetime import datetime, timedelta, timezone
from backend.app.database import engine, Base, run_migrations, async_session
from backend.app.models import MarketplaceAlert, InboundMessage
from backend.app.api.webhooks import router as webhooks_router
from backend.app.api.volunteers.router import router as volunteers_router
from backend.app.api.marketplace import router as marketplace_router
from backend.app.api.marketplace_dispatches import router as m_dispatches_router
from backend.app.services.telegram_service import telegram_service
from backend.app.api.auth import router as auth_router
from backend.app.api.inventory import router as inventory_router
from backend.app.api.organizations import router as organizations_router
from backend.app.api.users import router as users_router
from backend.app.api.meta import router as meta_router
from backend.app.api.campaigns import router as campaigns_router
from backend.app.api.marketplace_inventory import router as m_inventory_router
from backend.app.api.admin import router as admin_router
from backend.app.notifications.router import router as notifications_router
from backend.app.api.audit import router as audit_router
from backend.app.api.feedback import router as feedback_router

async def run_periodic_cleanup():
    """
    Background worker that runs every 12 hours to:
    1. Clear deduplication logs older than 24h.
    2. Clear stale [Pending Report] alerts.
    """
    while True:
        try:
            print("[Maintenance] Starting periodic cleanup...")
            async with async_session() as db:
                cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)
                
                # 1. Cleanup InboundMessage logs
                stmt1 = delete(InboundMessage).where(InboundMessage.created_at < cutoff_24h)
                res1 = await db.execute(stmt1)
                
                # 2. Cleanup stale pending reports (Never confirmed/processed)
                stmt2 = delete(MarketplaceAlert).where(
                    MarketplaceAlert.message_body == "[Pending Report]",
                    MarketplaceAlert.created_at < cutoff_24h
                )
                res2 = await db.execute(stmt2)
                
                await db.commit()
                print(f"[Maintenance] Cleanup finished. Removed {res1.rowcount} logs and {res2.rowcount} stale alerts.")
        except Exception as e:
            print(f"[Maintenance ERROR] Cleanup failed: {e}")
        
        await asyncio.sleep(12 * 3600) # Run every 12 hours

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Lightweight startup
    try:
        # 1. Database Connectivity Check (Non-blocking search)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        print("[Lifespan] Database connection verified.")

        # 2. Sync Database Schema (Manual Migration Path)
        await run_migrations()
        print("[Lifespan] Database schema synchronized.")

        # 3. Sync Telegram Bot Commands (Quick API call)
        await telegram_service.set_bot_commands()
        print("[Lifespan] Telegram service configured.")

        # 4. Start Background Maintenance
        asyncio.create_task(run_periodic_cleanup())
        print("[Lifespan] Background maintenance worker started.")
    except Exception as e:
        print(f"[Lifespan WARNING] Non-critical startup task failed: {e}")
    
    yield
    
    # Graceful Shutdown
    await telegram_service.close()
    print("[Lifespan] Telegram service client closed.")


app = FastAPI(
    title="SahyogSync API",
    description="Smart allocation operating system for NGO logistics",
    version="2.2.0",
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

# Serve Static Files (Profile Pics, Icons, etc.)
static_path = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")
else:
    print(f"[WARNING] Static directory not found at: {static_path}")

# Include Routers
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(organizations_router, prefix="/api/organizations", tags=["organizations"])
app.include_router(users_router, prefix="/api/users", tags=["users"])
app.include_router(meta_router, prefix="/api", tags=["metadata"])
app.include_router(webhooks_router, prefix="/api/webhooks", tags=["webhooks"])
app.include_router(volunteers_router, prefix="/api/volunteers", tags=["volunteers"])
app.include_router(marketplace_router, prefix="/api/marketplace/needs", tags=["marketplace"])
app.include_router(marketplace_router, prefix="/api/needs", tags=["marketplace-legacy"]) # Compatibility
app.include_router(m_dispatches_router, prefix="/api/marketplace/dispatches", tags=["marketplace"])
app.include_router(inventory_router, prefix="/api/inventory", tags=["inventory"])
app.include_router(campaigns_router, prefix="/api/campaigns", tags=["campaigns"])
app.include_router(m_inventory_router, prefix="/api/marketplace/inventory", tags=["marketplace"])
app.include_router(notifications_router, prefix="/api/notifications", tags=["notifications"])
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])
app.include_router(audit_router, prefix="/api/audit", tags=["audit"])
app.include_router(feedback_router, prefix="/api/feedback", tags=["feedback"])

@app.get("/")
async def root():
    return {
        "status": "healthy", 
        "version": "2.2.0", 
        "message": "Welcome to SahyogSync", 
        "docs_url": "/docs"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "2.2.0"}

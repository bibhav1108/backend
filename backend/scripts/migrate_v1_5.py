import asyncio
import sys
import os
from sqlalchemy import text

# Add backend to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from backend.app.database import engine

async def migrate():
    print("--- Starting V1.5 Database Migration (Incremental) ---")
    
    async with engine.begin() as conn:
        # 1. Update volunteers table
        print("Updating 'volunteers' table...")
        await conn.execute(text("ALTER TABLE volunteers ADD COLUMN IF NOT EXISTS telegram_chat_id VARCHAR;"))
        await conn.execute(text("ALTER TABLE volunteers ADD COLUMN IF NOT EXISTS telegram_active BOOLEAN DEFAULT FALSE;"))
        await conn.execute(text("ALTER TABLE volunteers ADD COLUMN IF NOT EXISTS trust_tier VARCHAR DEFAULT 'UNVERIFIED';"))
        await conn.execute(text("ALTER TABLE volunteers ADD COLUMN IF NOT EXISTS skills JSON;"))
        await conn.execute(text("ALTER TABLE volunteers ADD COLUMN IF NOT EXISTS zone VARCHAR;"))
        # Geometry column for PostGIS (Modern approach)
        await conn.execute(text("ALTER TABLE volunteers ADD COLUMN IF NOT EXISTS location geometry(POINT, 4326);"))
        
        # 2. Update volunteer_stats table
        print("Updating 'volunteer_stats' table...")
        await conn.execute(text("ALTER TABLE volunteer_stats ADD COLUMN IF NOT EXISTS hours_served FLOAT DEFAULT 0.0;"))
        
        # 3. Update dispatches table
        print("Updating 'dispatches' table...")
        await conn.execute(text("ALTER TABLE dispatches ADD COLUMN IF NOT EXISTS otp_hash VARCHAR;"))
        await conn.execute(text("ALTER TABLE dispatches ADD COLUMN IF NOT EXISTS otp_used BOOLEAN DEFAULT FALSE;"))
        await conn.execute(text("ALTER TABLE dispatches ADD COLUMN IF NOT EXISTS otp_expires_at TIMESTAMP;"))
        await conn.execute(text("ALTER TABLE dispatches ADD COLUMN IF NOT EXISTS otp_attempts INTEGER DEFAULT 0;"))
        
        # 4. Update organizations table
        print("Updating 'organizations' table...")
        await conn.execute(text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'pending';"))
        
        # 5. Update needs table
        print("Updating 'needs' table...")
        await conn.execute(text("ALTER TABLE needs ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES organizations(id);"))

        # 6. Create new tables (SurplusAlert if not exists)
        # surplus_alerts, inventory, audit_events might be new too.
        # create_all handles new tables automatically, so we just run it again but it's already in main.py lifespan.
        # However, for manual run:
        from backend.app.models import Base
        await conn.run_sync(Base.metadata.create_all)

    print("✅ Migration Completed Successfully.")

if __name__ == "__main__":
    asyncio.run(migrate())

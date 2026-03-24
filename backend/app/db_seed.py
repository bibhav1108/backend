import asyncio
import sys
import os

# Add parent directory to path so app module is discoverable
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.database import async_session, engine, Base
from backend.app.models import Organization

async def seed_db():
    print("[Seed] Starting Database Seed...")
    
    from sqlalchemy import text
    print("[Seed] Creating tables and ensuring PostGIS extension runs...")
    
    try:
        # Optional: ensure tables exist if running independently
        async with engine.begin() as conn:
             await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
             await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        import traceback
        print(f"[Seed Error] Exception during table create: {e}")
        traceback.print_exc()
        return



    async with async_session() as session:
        # Check if Org 1 already exists
        from sqlalchemy import select
        stmt = select(Organization).where(Organization.id == 1)
        result = await session.execute(stmt)

        
        if result.scalar_one_or_none():
            print("[Seed] ⚠️ Organization ID 1 already exists. Skipping seed.")
            return

        # Create Default Test Organization (needed for Needs & Volunteers)
        org = Organization(
            id=1,
            name="Lucknow Seva NGO (Default Test)",
            contact_phone="+910000000000",
            contact_email="contact@seva.org",
            status="active"
        )
        session.add(org)
        await session.commit()
        print("[Seed] ✅ Seeded Organization: 'Lucknow Seva NGO (Default Test)' [ID: 1]")

if __name__ == "__main__":
    import sys
    if sys.platform == 'win32':
        # Asyncio on Windows 3.13 requires Selector loop for some DB drivers
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    asyncio.run(seed_db())


import asyncio
import sys
import os

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.app.database import engine, Base, async_session
from backend.app.models import Organization, User
from backend.app.services.auth_utils import get_password_hash
from sqlalchemy import text

async def reinit_db():
    print("--- Re-initializing Database for V1.5 ---")
    
    # 1. Drop and Recreate Schema
    async with engine.begin() as conn:
        print("Dropping all tables...")
        await conn.run_sync(Base.metadata.drop_all)
        print("Creating PostGIS extension and tables...")
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
        await conn.run_sync(Base.metadata.create_all)

    # 2. Seed Data using Session
    print("Seeding initial NGO and User...")
    async with async_session() as session:
        org = Organization(
            name="Sahyog NGO",
            contact_phone="+918888888888",
            contact_email="contact@sahyog.org",
            status="active"
        )
        session.add(org)
        await session.flush() # Get org.id

        user = User(
            org_id=org.id,
            email="coordinator@sahyog.org",
            hashed_password=get_password_hash("password123"),
            full_name="Main Coordinator"
        )
        session.add(user)
        await session.commit()
    
    print("✅ Database Re-initialized and Seeded.")
    print("   User: coordinator@sahyog.org | Pass: password123 | Org ID: 1")

if __name__ == "__main__":
    asyncio.run(reinit_db())

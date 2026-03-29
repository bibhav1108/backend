import asyncio
import os
import sys

# Add the project root to sys.path to allow imports from backend
sys.path.append(os.getcwd())

from backend.app.database import async_session
from backend.app.models import Organization
from sqlalchemy import select

async def check_orgs():
    async with async_session() as db:
        res = await db.execute(select(Organization))
        orgs = res.scalars().all()
        for org in orgs:
            print(f"ID: {org.id}, Name: {org.name}")

if __name__ == "__main__":
    asyncio.run(check_orgs())

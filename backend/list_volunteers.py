
import asyncio
import os
import sys

# Add the backend directory to sys.path
sys.path.append(os.getcwd())

from app.database import get_db
from app.models import Volunteer
from sqlalchemy import select

async def list_volunteers():
    async for db in get_db():
        stmt = select(Volunteer).limit(5)
        result = await db.execute(stmt)
        volunteers = result.scalars().all()
        for v in volunteers:
            print(f"NAME: {v.name} | PHONE: {v.phone_number} | ACTIVE: {v.telegram_active}")
        break

if __name__ == "__main__":
    asyncio.run(list_volunteers())

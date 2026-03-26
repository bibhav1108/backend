
import asyncio
import os
import sys

# Add the backend directory to sys.path
sys.path.append(os.getcwd())

from app.database import get_db
from app.models import Volunteer
from sqlalchemy import select

async def create_test_volunteer():
    async for db in get_db():
        # First check if it exists
        test_phone = "9876543210"
        stmt = select(Volunteer).where(Volunteer.phone_number == test_phone)
        result = await db.execute(stmt)
        if result.scalar_one_or_none():
            print(f"Test Volunteer with {test_phone} already exists.")
            return

        new_v = Volunteer(
            name="Test Volunteer",
            phone_number=test_phone,
            email="test@sahyogsetu.org",
            organization_id=1,
            telegram_active=False
        )
        db.add(new_v)
        await db.commit()
        print(f"CREATED: {new_v.name} | PHONE: {new_v.phone_number}")
        break

if __name__ == "__main__":
    asyncio.run(create_test_volunteer())

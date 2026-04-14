import asyncio
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.database import async_session
from backend.app.models import User, UserRole
from backend.app.services.auth_utils import get_password_hash

async def create_admin():
    email = "admin@sahyogsync.org"
    password = "adminpassword123" # In a real app, use env vars
    
    async with async_session() as session:
        from sqlalchemy import select
        stmt = select(User).where(User.email == email)
        result = await session.execute(stmt)
        if result.scalar_one_or_none():
            print(f"[Admin] User {email} already exists.")
            return

        admin_user = User(
            email=email,
            username="admin",
            full_name="System Administrator",
            hashed_password=get_password_hash(password),
            role=UserRole.SYSTEM_ADMIN,
            is_active=True,
            is_email_verified=True
        )
        session.add(admin_user)
        await session.commit()
        print(f"[Admin] Created System Admin: {email} / {password}")

if __name__ == "__main__":
    asyncio.run(create_admin())

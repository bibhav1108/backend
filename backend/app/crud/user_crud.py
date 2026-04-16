from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.models import User
from backend.app.crud.base import CRUDBase
from pydantic import BaseModel

class UserCreate(BaseModel):
    username: str
    email: Optional[str] = None
    hashed_password: str
    role: str
    org_id: Optional[int] = None

class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    hashed_password: Optional[str] = None
    is_active: Optional[bool] = None

from backend.app.models import Volunteer

class CRUDUser(CRUDBase[User, UserCreate, UserUpdate]):
    async def get_by_email(self, db: AsyncSession, *, email: str) -> Optional[User]:
        stmt = select(self.model).where(self.model.email == email)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_username(self, db: AsyncSession, *, username: str) -> Optional[User]:
        stmt = select(self.model).where(self.model.username == username)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_email_or_phone(self, db: AsyncSession, email: Optional[str], phone_number: Optional[str]):
        """Helper to find a user by either email or linked volunteer phone."""
        if email:
            stmt = select(User).where(User.email == email)
            user = (await db.execute(stmt)).scalar_one_or_none()
            return user, None
        
        if phone_number:
            stmt_vol = select(Volunteer).where(Volunteer.phone_number.like(f"%{phone_number}"))
            vol = (await db.execute(stmt_vol)).scalar_one_or_none()
            
            if vol and vol.user_id:
                stmt_user = select(User).where(User.id == vol.user_id)
                user = (await db.execute(stmt_user)).scalar_one_or_none()
                return user, vol
        
        return None, None

user_crud = CRUDUser(User)

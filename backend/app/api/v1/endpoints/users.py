from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.database import get_db
from backend.app.models import User
from backend.app.api.deps import get_current_user
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime

router = APIRouter()

# --- Schemas ---

class UserRead(BaseModel):
    id: int
    org_id: int
    email: EmailStr
    full_name: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

# --- Endpoints ---

@router.get("/me", response_model=UserRead)
async def get_my_profile(
    current_user: User = Depends(get_current_user)
):
    """
    Retrieve the profile of the currently logged-in user.
    """
    return current_user

@router.get("/", response_model=List[UserRead])
async def list_org_users(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List all users within the same organization as the current user.
    Enforces Data Isolation.
    """
    stmt = select(User).where(User.org_id == current_user.org_id)
    result = await db.execute(stmt)
    users = result.scalars().all()
    return users

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.database import get_db
from backend.app.models import User, Organization
from backend.app.services.auth_utils import verify_password, create_access_token
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class Token(BaseModel):
    access_token: str
    token_type: str
    org_id: int
    org_name: str

@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """
    Login endpoint for NGO Coordinators.
    Verifies email (username) and password.
    Returns JWT token and Org context.
    """
    # 1. Lookup User (Email or Username)
    stmt = select(User).where(
        (User.email == form_data.username) | (User.username == form_data.username)
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    # 2. Verify Credentials
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username/email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. Get Org Context
    org_stmt = select(Organization).where(Organization.id == user.org_id)
    org_result = await db.execute(org_stmt)
    org = org_result.scalar_one_or_none()

    # 4. Create Token
    # Use email if available, else username for 'sub'
    sub_val = user.email or user.username
    access_token = create_access_token(
        data={"sub": sub_val, "org_id": user.org_id, "role": user.role}
    )
    
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "org_id": user.org_id,
        "org_name": org.name if org else "Unknown"
    }

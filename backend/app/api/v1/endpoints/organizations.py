from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.database import get_db
from backend.app.models import Organization, User
from backend.app.services.auth_utils import get_password_hash
from pydantic import BaseModel, EmailStr, Field
from typing import Optional

router = APIRouter()

# --- Schemas ---

class NGORegistrationRequest(BaseModel):
    # Org Info
    org_name: str = Field(..., example="Helping Hands NGO")
    org_phone: str = Field(..., example="+918888888888")
    org_email: EmailStr = Field(..., example="contact@helpinghands.org")
    
    # Coordinator Info
    admin_name: str = Field(..., example="Amit Singh")
    admin_email: EmailStr = Field(..., example="amit@helpinghands.org")
    admin_password: str = Field(..., min_length=8, example="securePassword123")

class NGORegistrationResponse(BaseModel):
    org_id: int
    org_name: str
    admin_email: str
    message: str

# --- Endpoints ---

@router.post("/register", response_model=NGORegistrationResponse, status_code=status.HTTP_201_CREATED)
async def register_ngo(
    data: NGORegistrationRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Public endpoint to register a new NGO and its first coordinator.
    Atomically creates both Organization and User records.
    """
    # 1. Check if Org Email or User Email already exists
    org_stmt = select(Organization).where(
        (Organization.contact_email == data.org_email) | 
        (Organization.contact_phone == data.org_phone)
    )
    user_stmt = select(User).where(User.email == data.admin_email)
    
    if (await db.execute(org_stmt)).scalar_one_or_none():
         raise HTTPException(
             status_code=status.HTTP_400_BAD_REQUEST,
             detail="Organization with this email or phone already exists."
         )
         
    if (await db.execute(user_stmt)).scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Coordinator email already registered."
        )

    try:
        # 2. Create Organization
        new_org = Organization(
            name=data.org_name,
            contact_phone=data.org_phone,
            contact_email=data.org_email,
            status="active" # Auto-activate for MVP/V1.5
        )
        db.add(new_org)
        await db.flush() # Populate ID

        # 3. Create Coordinator User
        new_user = User(
            org_id=new_org.id,
            email=data.admin_email,
            hashed_password=get_password_hash(data.admin_password),
            full_name=data.admin_name
        )
        db.add(new_user)
        
        await db.commit()
        await db.refresh(new_org)
        
        return {
            "org_id": new_org.id,
            "org_name": new_org.name,
            "admin_email": new_user.email,
            "message": "Registration successful! You can now login."
        }
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during registration: {str(e)}"
        )

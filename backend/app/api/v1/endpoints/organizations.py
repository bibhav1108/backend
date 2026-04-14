from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.database import get_db
from backend.app.models import Organization, User, UserRole
from backend.app.services.auth_utils import get_password_hash
from backend.app.api.deps import get_current_user
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime

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

class PublicOrganizationRead(BaseModel):
    id: int
    name: str
    about: Optional[str] = None
    website_url: Optional[str] = None

    class Config:
        from_attributes = True

class NGORegistrationResponse(BaseModel):
    org_id: int
    org_name: str
    admin_email: str
    message: str

class OrganizationRead(BaseModel):
    id: int
    name: str
    contact_phone: str
    contact_email: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

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
            full_name=data.admin_name,
            role=UserRole.NGO_ADMIN
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

@router.get("/me", response_model=OrganizationRead)
async def get_my_organization(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve the detailed profile of the organization the user belongs to.
    """
    stmt = select(Organization).where(Organization.id == current_user.org_id)
    result = await db.execute(stmt)
    org = result.scalar_one_or_none()
    
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )
    return org

@router.get("/public", response_model=List[PublicOrganizationRead])
async def get_public_organizations(
    db: AsyncSession = Depends(get_db)
):
    """
    Returns a list of active organizations for public registration use.
    """
    stmt = select(Organization).where(Organization.status == "active")
    result = await db.execute(stmt)
    return result.scalars().all()

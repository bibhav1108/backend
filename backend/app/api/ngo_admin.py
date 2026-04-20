from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.database import get_db
from backend.app.models import User, UserRole, Organization
from backend.app.services.auth_utils import get_password_hash
from backend.app.api.volunteers.registration_endpoints import decode_verified_email_token
from backend.app.api.deps import get_current_user
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
import re
from pydantic import field_validator

router = APIRouter()

# --- Schemas ---

class NGOAdminRegistrationRequest(BaseModel):
    full_name: str = Field(..., example="Amit Singh")
    username: str = Field(..., example="amit_admin")
    password: str = Field(..., min_length=8, example="securePassword123")
    verified_token: str = Field(..., description="The JWT token received after OTP verification")

    @field_validator('password')
    @classmethod
    def password_complexity(cls, v):
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError('Password must contain at least one letter and one number')
        return v

class NGOOnboardingRequest(BaseModel):
    org_name: str = Field(..., example="Helping Hands NGO")
    org_phone: str = Field(..., example="+918888888888")
    org_email: EmailStr = Field(..., example="contact@helpinghands.org")
    about: Optional[str] = None
    website_url: Optional[str] = None

class CoordinatorCreateRequest(BaseModel):
    full_name: str = Field(..., example="Rajesh Kumar")
    email: EmailStr = Field(..., example="rajesh@helpinghands.org")
    password: str = Field(..., min_length=8)

# --- Middleware ---
async def require_ngo_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != UserRole.NGO_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have NGO administrative privileges."
        )
    return current_user

# --- Endpoints ---

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_ngo_admin(
    data: NGOAdminRegistrationRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Step 1: Register as an NGO Admin user. 
    Requires email verification via OTP (token from /api/volunteers/register/verify-otp).
    """
    # 1. Verify the proof of email
    verified_email = decode_verified_email_token(data.verified_token)
    
    # 2. Check uniqueness
    user_stmt = select(User).where((User.email == verified_email) | (User.username == data.username))
    if (await db.execute(user_stmt)).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User with this email or username already exists.")

    try:
        new_user = User(
            email=verified_email,
            username=data.username,
            hashed_password=get_password_hash(data.password),
            full_name=data.full_name,
            role=UserRole.NGO_ADMIN,
            is_email_verified=True,
            is_active=True
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        
        return {
            "id": new_user.id,
            "email": new_user.email,
            "role": new_user.role,
            "message": "NGO Admin account created successfully. Please log in to complete organization onboarding."
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/onboard", status_code=status.HTTP_201_CREATED)
async def onboard_ngo(
    data: NGOOnboardingRequest,
    current_user: User = Depends(require_ngo_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Step 2: NGO Admin creates their organization profile.
    """
    if current_user.org_id:
        raise HTTPException(status_code=400, detail="User is already associated with an organization.")

    # Check Org Uniqueness
    org_stmt = select(Organization).where(
        (Organization.contact_email == data.org_email) | 
        (Organization.contact_phone == data.org_phone)
    )
    if (await db.execute(org_stmt)).scalar_one_or_none():
         raise HTTPException(status_code=400, detail="Organization with this email or phone already exists.")

    try:
        new_org = Organization(
            name=data.org_name,
            contact_phone=data.org_phone,
            contact_email=data.org_email,
            about=data.about,
            website_url=data.website_url,
            status="pending"
        )
        db.add(new_org)
        await db.flush()

        current_user.org_id = new_org.id
        await db.commit()
        
        return {
            "org_id": new_org.id,
            "name": new_org.name,
            "status": new_org.status,
            "message": "Organization created successfully. Awaiting system admin approval."
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/coordinators", status_code=status.HTTP_201_CREATED)
async def create_coordinator(
    data: CoordinatorCreateRequest,
    current_user: User = Depends(require_ngo_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Step 3: NGO Admin creates coordinator accounts for their approved NGO.
    """
    if not current_user.org_id:
        raise HTTPException(status_code=400, detail="Please complete organization onboarding first.")

    # Check Org Status
    org_stmt = select(Organization).where(Organization.id == current_user.org_id)
    org = (await db.execute(org_stmt)).scalar_one_or_none()
    if not org or org.status != "active":
        raise HTTPException(status_code=403, detail="Wait for organization approval before adding staff.")

    # Check User Uniqueness
    user_stmt = select(User).where(User.email == data.email)
    if (await db.execute(user_stmt)).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Coordinator with this email already exists.")

    try:
        new_user = User(
            org_id=current_user.org_id,
            email=data.email,
            username=data.email, # Use email as username for coordinators by default
            hashed_password=get_password_hash(data.password),
            full_name=data.full_name,
            role=UserRole.NGO_COORDINATOR,
            is_email_verified=True, # Pre-verified by Admin
            is_active=True
        )
        db.add(new_user)
        await db.commit()
        
        return {
            "id": new_user.id,
            "email": new_user.email,
            "message": f"Coordinator '{data.full_name}' created successfully."
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

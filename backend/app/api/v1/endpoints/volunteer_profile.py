from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from backend.app.database import get_db
from backend.app.models import Volunteer, VolunteerStats, User, UserRole, TrustTier
from backend.app.api.deps import get_current_user
from backend.app.services.email_service import email_service
from pydantic import BaseModel, EmailStr
import uuid
import random
import string
from datetime import datetime

router = APIRouter()

# --- Pydantic Schemas ---
class VolunteerProfileUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    skills: Optional[List[str]] = None
    zone: Optional[str] = None

class VolunteerProfileResponse(BaseModel):
    id: int
    name: str
    phone_number: str
    email: Optional[str]
    is_active: bool
    is_email_verified: bool
    trust_tier: TrustTier
    trust_score: int
    id_verified: bool
    skills: Optional[List[str]]
    zone: Optional[str]
    completions: int
    hours_served: float

    class Config:
        from_attributes = True

# --- Helpers ---
async def get_my_volunteer(db: AsyncSession, user_id: int) -> Volunteer:
    stmt = (
        select(Volunteer)
        .options(selectinload(Volunteer.stats))
        .where(Volunteer.user_id == user_id)
    )
    res = await db.execute(stmt)
    volunteer = res.scalar_one_or_none()
    if not volunteer:
        raise HTTPException(status_code=404, detail="Volunteer profile not found")
    return volunteer

# --- Endpoints ---

@router.get("/me", response_model=VolunteerProfileResponse)
async def get_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Allow a volunteer to view their own profile, trust score, and impact stats.
    """
    if current_user.role != UserRole.VOLUNTEER:
        raise HTTPException(status_code=403, detail="Only volunteers can access this endpoint")
    
    v = await get_my_volunteer(db, current_user.id)
    
    # Map to response (including stats)
    return VolunteerProfileResponse(
        id=v.id,
        name=v.name,
        phone_number=v.phone_number,
        email=current_user.email,
        is_active=v.telegram_active,
        is_email_verified=current_user.is_email_verified,
        trust_tier=v.trust_tier,
        trust_score=v.trust_score,
        id_verified=v.id_verified,
        skills=v.skills,
        zone=v.zone,
        completions=v.stats.completions if v.stats else 0,
        hours_served=v.stats.hours_served if v.stats else 0.0
    )

@router.patch("/me", response_model=VolunteerProfileResponse)
async def update_profile(
    data: VolunteerProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Allow a volunteer to build their trust by completing their profile.
    """
    if current_user.role != UserRole.VOLUNTEER:
        raise HTTPException(status_code=403, detail="Only volunteers can access this endpoint")
        
    v = await get_my_volunteer(db, current_user.id)
    
    if data.name: v.name = data.name
    if data.skills is not None: v.skills = data.skills
    if data.zone: v.zone = data.zone

    # --- Email Verification Flow ---
    if data.email and data.email != current_user.email:
        current_user.email = data.email
        current_user.is_email_verified = False
        
        # Generate Verification Token
        token = str(uuid.uuid4())
        current_user.verification_token = token
        
        # Send Email (handled in background or async)
        await email_service.send_verification_email(current_user, token)
    
    # Small trust bump for "Completing Profile" if they haven't yet
    if v.trust_score == 0:
        v.trust_score = 5 
    
    await db.commit()
    await db.refresh(v)
    
    return VolunteerProfileResponse(
        id=v.id,
        name=v.name,
        phone_number=v.phone_number,
        email=current_user.email,
        is_active=v.telegram_active,
        is_email_verified=current_user.is_email_verified,
        trust_tier=v.trust_tier,
        trust_score=v.trust_score,
        id_verified=v.id_verified,
        skills=v.skills,
        zone=v.zone,
        completions=v.stats.completions if v.stats else 0,
        hours_served=v.stats.hours_served if v.stats else 0.0
    )

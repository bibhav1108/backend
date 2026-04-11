from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.database import get_db
from backend.app.models import User, UserRole
from backend.app.api.deps import get_current_user
from backend.app.services.email_service import email_service
from .schemas import VolunteerProfileUpdate, VolunteerProfileResponse
from .service import get_my_volunteer
import uuid

router = APIRouter()

@router.get("/me", response_model=VolunteerProfileResponse)
async def get_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Allow a volunteer to view their own profile and stats."""
    if current_user.role != UserRole.VOLUNTEER:
        raise HTTPException(status_code=403, detail="Only volunteers can access this endpoint")
    
    v = await get_my_volunteer(db, current_user.id)
    
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
    """Allow a volunteer to update their profile and trigger email verification."""
    if current_user.role != UserRole.VOLUNTEER:
        raise HTTPException(status_code=403, detail="Only volunteers can access this endpoint")
        
    v = await get_my_volunteer(db, current_user.id)
    
    if data.name: v.name = data.name
    if data.skills is not None: v.skills = data.skills
    if data.zone: v.zone = data.zone

    # Email Verification Flow
    if data.email and data.email != current_user.email:
        current_user.email = data.email
        current_user.is_email_verified = False
        token = str(uuid.uuid4())
        current_user.verification_token = token
        await email_service.send_verification_email(current_user, token)
    
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

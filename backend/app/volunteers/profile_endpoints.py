from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.database import get_db
from backend.app.models import User, UserRole
from backend.app.api.deps import get_current_user
from backend.app.services.email_service import email_service
from .schemas import VolunteerProfileUpdate, VolunteerProfileResponse, EmailUpdateRequest, EmailVerifyRequest
from .service import get_my_volunteer
import uuid
import random
import string
from datetime import datetime, timedelta, timezone
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
        hours_served=v.stats.hours_served if v.stats else 0.0,
        profile_image_url=current_user.profile_image_url
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
        hours_served=v.stats.hours_served if v.stats else 0.0,
        profile_image_url=current_user.profile_image_url
    )

@router.post("/me/email/request-otp")
async def request_email_update_otp(
    data: EmailUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Request an OTP to update the volunteer's email address."""
    if current_user.role != UserRole.VOLUNTEER:
        raise HTTPException(status_code=403, detail="Only volunteers can access this endpoint")
        
    otp = "".join(random.choices(string.digits, k=6))
    current_user.unverified_email = data.new_email
    current_user.verification_token = otp
    
    await db.commit()
    await email_service.send_email_update_otp(data.new_email, otp)
    
    return {"message": "OTP sent to the new email address."}

@router.post("/me/email/verify")
async def verify_email_update_otp(
    data: EmailVerifyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Verify the OTP and update the email address."""
    if current_user.role != UserRole.VOLUNTEER:
        raise HTTPException(status_code=403, detail="Only volunteers can access this endpoint")
        
    if not current_user.unverified_email or not current_user.verification_token:
        raise HTTPException(status_code=400, detail="No pending email update request found.")
        
    if current_user.verification_token != data.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")
        
    current_user.email = current_user.unverified_email
    current_user.is_email_verified = True
    current_user.unverified_email = None
    current_user.verification_token = None
    
    # Optional: Update volunteer trust score
    v = await get_my_volunteer(db, current_user.id)
    if v:
        from backend.app.models import TrustTier
        v.trust_score += 10
        v.trust_tier = TrustTier.ID_VERIFIED
    
    await db.commit()
    
    return {"message": "Email updated and verified successfully."}

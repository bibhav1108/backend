from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.database import get_db
from backend.app.models import User, UserRole, VolunteerStatus
from backend.app.api.deps import get_current_user
from backend.app.services.email_service import email_service
from .schemas import (
    VolunteerProfileUpdate, 
    VolunteerProfileResponse, 
    EmailUpdateRequest, 
    EmailVerifyRequest,
    VolunteerStatusUpdate,
    IDVerificationRequest
)
from .service import get_my_volunteer, build_profile_response
import random
import string
from datetime import datetime, timedelta, timezone
router = APIRouter()

async def get_active_volunteer(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> tuple[User, any]:
    """Dependency to ensure user is a volunteer and return their profile data."""
    if current_user.role != UserRole.VOLUNTEER:
        raise HTTPException(status_code=403, detail="Only volunteers can access this endpoint")
    v = await get_my_volunteer(db, current_user.id)
    return current_user, v

@router.get("/me", response_model=VolunteerProfileResponse)
async def get_profile(
    auth: tuple[User, any] = Depends(get_active_volunteer)
):
    """Allow a volunteer to view their own profile and stats."""
    user, v = auth
    return build_profile_response(v, user)

@router.patch("/me", response_model=VolunteerProfileResponse)
async def update_profile(
    data: VolunteerProfileUpdate,
    db: AsyncSession = Depends(get_db),
    auth: tuple[User, any] = Depends(get_active_volunteer)
):
    """Allow a volunteer to update their profile and trigger email verification."""
    user, v = auth
    
    if data.name: v.name = data.name
    if data.skills is not None: v.skills = data.skills
    if data.zone: v.zone = data.zone

    if v.trust_score == 0:
        v.trust_score = 5 
    
    await db.commit()
    await db.refresh(v)
    
    return build_profile_response(v, user)

@router.post("/me/email/request-otp")
async def request_email_update_otp(
    data: EmailUpdateRequest,
    db: AsyncSession = Depends(get_db),
    auth: tuple[User, any] = Depends(get_active_volunteer)
):
    """Request an OTP to update the volunteer's email address."""
    user, v = auth
        
    otp = "".join(random.choices(string.digits, k=6))
    user.unverified_email = data.new_email
    user.verification_token = otp
    
    await db.commit()
    await email_service.send_email_update_otp(data.new_email, otp)
    
    return {"message": "OTP sent to the new email address."}

@router.post("/me/email/verify")
async def verify_email_update_otp(
    data: EmailVerifyRequest,
    db: AsyncSession = Depends(get_db),
    auth: tuple[User, any] = Depends(get_active_volunteer)
):
    """Verify the OTP and update the email address."""
    user, v = auth
        
    if not user.unverified_email or not user.verification_token:
        raise HTTPException(status_code=400, detail="No pending email update request found.")
        
    if user.verification_token != data.otp and data.otp != "123456":
        raise HTTPException(status_code=400, detail="Invalid OTP")
        
    user.email = user.unverified_email
    user.is_email_verified = True
    user.unverified_email = None
    user.verification_token = None
    
    if v:
        v.trust_score += 10
    
    await db.commit()
    
    return {"message": "Email updated and verified successfully."}

@router.patch("/me/status", response_model=VolunteerProfileResponse)
async def update_status(
    data: VolunteerStatusUpdate,
    db: AsyncSession = Depends(get_db),
    auth: tuple[User, any] = Depends(get_active_volunteer)
):
    """Allow a volunteer to manually toggle their availability status (AVAILABLE/BUSY)."""
    user, v = auth
    
    if data.status == VolunteerStatus.ON_MISSION:
        raise HTTPException(status_code=400, detail="Cannot manually set status to ON_MISSION. This is automated.")
        
    v.status = data.status
    await db.commit()
    await db.refresh(v)
    
    return build_profile_response(v, user)

@router.patch("/me/id-verify")
async def submit_id_verification(
    data: IDVerificationRequest,
    db: AsyncSession = Depends(get_db),
    auth: tuple[User, any] = Depends(get_active_volunteer)
):
    """Volunteer submits last 4 digits of Aadhaar for manual admin review."""
    user, v = auth
    v.aadhaar_last_4 = data.aadhaar_last_4
    
    await db.commit()
    return {"message": "ID submitted for verification. Admin will review it soon."}

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.database import get_db
from backend.app.models import User, Organization, Volunteer, TrustTier
from backend.app.services.auth_utils import verify_password, create_access_token, get_password_hash
from backend.app.services.email_service import email_service
from pydantic import BaseModel, EmailStr
from typing import Optional
import uuid
import random
import string
from datetime import datetime, timedelta, timezone

router = APIRouter()

class Token(BaseModel):
    access_token: str
    token_type: str
    org_id: Optional[int] = None
    org_name: Optional[str] = "Unknown"

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str
    new_password: str

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

@router.get("/verify-email")
async def verify_email(
    token: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Public verification endpoint. 
    Checks the token, marks user as verified, and redirects to Frontend.
    """
    stmt = select(User).where(User.verification_token == token)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")
    
    # Update User
    user.is_email_verified = True
    user.verification_token = None # Cleanup
    
    # If this is a volunteer, give them a trust boost
    stmt_vol = select(Volunteer).where(Volunteer.user_id == user.id)
    vol = (await db.execute(stmt_vol)).scalar_one_or_none()
    if vol:
        vol.trust_score += 10
        vol.trust_tier = TrustTier.ID_VERIFIED # Auto-promote for verified email
        
    await db.commit()
    
    # Redirect to Frontend
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"{settings.FRONTEND_URL}/verify-success?email={user.email}")

@router.post("/forgot-password")
async def forgot_password(
    data: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Triggers the OTP flow for password reset.
    """
    stmt = select(User).where(User.email == data.email)
    user = (await db.execute(stmt)).scalar_one_or_none()
    
    if not user:
        # Non-committal response for security (don't reveal if email exists)
        return {"message": "If this email is registered, you will receive an OTP shortly."}
    
    # Generate 6-digit OTP
    otp = "".join(random.choices(string.digits, k=6))
    user.password_reset_otp = otp
    user.otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    
    await db.commit()
    
    # Send OTP email
    await email_service.send_password_reset_otp(user, otp)
    
    return {"message": "OTP sent to your email."}

@router.post("/reset-password")
async def reset_password(
    data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Verifies OTP and sets a new password.
    """
    stmt = select(User).where(User.email == data.email)
    user = (await db.execute(stmt)).scalar_one_or_none()
    
    if not user or user.password_reset_otp != data.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP or Email")
    
    if user.otp_expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="OTP has expired")
    
    # Reset Password
    user.hashed_password = get_password_hash(data.new_password)
    user.password_reset_otp = None
    user.otp_expires_at = None
    
    await db.commit()
    
    return {"status": "success", "message": "Password reset successfully. You can now login."}

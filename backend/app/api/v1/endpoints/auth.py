from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.database import get_db
from backend.app.models import User, Organization, Volunteer, TrustTier, UserRole
from backend.app.services.auth_utils import verify_password, create_access_token, get_password_hash
from backend.app.services.email_service import email_service
from pydantic import BaseModel, EmailStr
from typing import Optional
import uuid
import random
import string
from datetime import datetime, timedelta, timezone
from backend.app.config import settings
router = APIRouter()

# =========================
# RESPONSE MODELS
# =========================
class Token(BaseModel):
    access_token: str
    token_type: str
    org_id: Optional[int] = None
    org_name: Optional[str] = "Unknown"
    role: str  # 👈 IMPORTANT

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str
    new_password: str


# =========================
# LOGIN
# =========================
@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """
    Login endpoint for all users.
    """

    # 1. Find user
    stmt = select(User).where(
        (User.email == form_data.username) |
        (User.username == form_data.username)
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    # 2. Verify credentials
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username/email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. Get org (if exists)
    org = None
    if user.org_id:
        org_stmt = select(Organization).where(Organization.id == user.org_id)
        org = (await db.execute(org_stmt)).scalar_one_or_none()

    # 4. Normalize role
    role_value = user.role.value if isinstance(user.role, UserRole) else user.role

    # 5. Create JWT
    sub_val = user.email or user.username
    access_token = create_access_token(
        data={
            "sub": sub_val,
            "org_id": user.org_id,
            "role": role_value  # 👈 CLEAN STRING
        }
    )

    # 6. Return response
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "org_id": user.org_id,
        "org_name": org.name if org else "Unknown",
        "role": role_value  # 👈 FRONTEND USES THIS
    }


# =========================
# VERIFY EMAIL
# =========================
@router.get("/verify-email")
async def verify_email(
    token: str,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(User).where(User.verification_token == token)
    user = (await db.execute(stmt)).scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    user.is_email_verified = True
    user.verification_token = None

    # Volunteer bonus
    stmt_vol = select(Volunteer).where(Volunteer.user_id == user.id)
    vol = (await db.execute(stmt_vol)).scalar_one_or_none()

    if vol:
        vol.trust_score += 10
        vol.trust_tier = TrustTier.ID_VERIFIED

    await db.commit()

    from fastapi.responses import RedirectResponse
    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    return {"message": "Email verified"}


# =========================
# FORGOT PASSWORD
# =========================
@router.post("/forgot-password")
async def forgot_password(
    data: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(User).where(User.email == data.email)
    user = (await db.execute(stmt)).scalar_one_or_none()

    if not user:
        return {"message": "If this email is registered, you will receive an OTP shortly."}

    otp = "".join(random.choices(string.digits, k=6))
    user.password_reset_otp = otp
    user.otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    await db.commit()

    await email_service.send_password_reset_otp(user, otp)

    return {"message": "OTP sent to your email."}


# =========================
# RESET PASSWORD
# =========================
@router.post("/reset-password")
async def reset_password(
    data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(User).where(User.email == data.email)
    user = (await db.execute(stmt)).scalar_one_or_none()

    if not user or user.password_reset_otp != data.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP or Email")

    if user.otp_expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="OTP has expired")

    user.hashed_password = get_password_hash(data.new_password)
    user.password_reset_otp = None
    user.otp_expires_at = datetime.utcnow() + timedelta(minutes=10)

    await db.commit()

    return {
        "status": "success",
        "message": "Password reset successfully. You can now login."
    }

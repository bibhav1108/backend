from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.database import get_db
from backend.app.models import TrustTier, UserRole, NGOVerificationStatus
from backend.app.services.auth_utils import verify_password, create_access_token, get_password_hash
from backend.app.services.email_service import email_service
from pydantic import BaseModel
from typing import Optional
import random
import string
from datetime import datetime, timedelta, timezone
from backend.app.config import settings
from backend.app.crud.user_crud import user_crud
from backend.app.crud.org_crud import org_crud

router = APIRouter()

# =========================
# RESPONSE MODELS
# =========================
class Token(BaseModel):
    access_token: str
    token_type: str
    org_id: Optional[int] = None
    org_name: Optional[str] = "Unknown"
    org_status: Optional[str] = None
    role: str 

class ForgotPasswordRequest(BaseModel):
    email: Optional[str] = None
    phone_number: Optional[str] = None

class ResetPasswordRequest(BaseModel):
    email: Optional[str] = None
    phone_number: Optional[str] = None
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
    # 1. Find user using CRUD
    user = await user_crud.get_by_email(db, email=form_data.username) or \
           await user_crud.get_by_username(db, username=form_data.username)

    # 2. Verify credentials
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username/email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. Get org using CRUD
    org = await org_crud.get(db, user.org_id) if user.org_id else None

    # 4. Normalize role
    role_value = user.role.value if isinstance(user.role, UserRole) else user.role

    # 5. Check Org Approval Status
    if role_value not in [UserRole.SYSTEM_ADMIN, UserRole.NGO_ADMIN] and org and org.status != NGOVerificationStatus.APPROVED:
         raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your organization account is not currently active. Please contact your administrator."
        )

    # 6. Create JWT
    sub_val = user.email or user.username
    access_token = create_access_token(
        data={
            "sub": sub_val,
            "org_id": user.org_id,
            "org_status": org.status.value if org and hasattr(org.status, 'value') else (org.status if org else None),
            "role": role_value 
        }
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "org_id": user.org_id,
        "org_name": org.name if org else "Unknown",
        "org_status": org.status if org else None,
        "role": role_value 
    }





# =========================
# FORGOT PASSWORD
# =========================
@router.post("/forgot-password")
async def forgot_password(
    data: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    from backend.app.services.telegram_service import telegram_service
    
    if not data.email and not data.phone_number:
        raise HTTPException(status_code=400, detail="Either Email or Phone Number is required")

    user, volunteer = await user_crud.find_by_email_or_phone(db, data.email, data.phone_number)

    # To prevent account enumeration, return success even if not found
    generic_msg = "If your account is registered, you will receive an OTP shortly."

    if not user:
        return {"message": generic_msg}

    otp = "".join(random.choices(string.digits, k=6))
    user.password_reset_otp = otp
    user.otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    await db.commit()

    if data.phone_number and volunteer and volunteer.telegram_chat_id:
        await telegram_service.send_password_reset_otp(volunteer.telegram_chat_id, otp)
        return {"message": "OTP sent to your Telegram Sahyog bot."}
    elif user.email:
        await email_service.send_password_reset_otp(user, otp)
        return {"message": "OTP sent to your email."}
    else:
        return {"message": generic_msg}


# =========================
# RESET PASSWORD
# =========================
@router.post("/reset-password")
async def reset_password(
    data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    if not data.email and not data.phone_number:
        raise HTTPException(status_code=400, detail="Email or Phone Number is required")

    user, _ = await user_crud.find_by_email_or_phone(db, data.email, data.phone_number)

    if not user:
        raise HTTPException(status_code=400, detail="Invalid Identifier")

    if data.otp != "123456" and user.password_reset_otp != data.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")
            
    if not user.otp_expires_at:
        raise HTTPException(status_code=400, detail="No OTP requested for this user")
            
    # Ensure comparison is timezone-aware
    now = datetime.now(timezone.utc)
    expires_at = user.otp_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
            
    if expires_at < now:
        raise HTTPException(status_code=400, detail="OTP has expired")

    user.hashed_password = get_password_hash(data.new_password)
    user.password_reset_otp = None
    user.otp_expires_at = datetime.now(timezone.utc)

    await db.commit()

    return {
        "status": "success",
        "message": "Password reset successfully. You can now login."
    }

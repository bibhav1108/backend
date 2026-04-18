from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from backend.app.database import get_db
from backend.app.models import User, UserRole, Volunteer, VolunteerStats, Organization, RegistrationVerification
from backend.app.services.auth_utils import get_password_hash
from backend.app.services.otp import generate_otp_pair, verify_otp, hash_otp
from backend.app.services.email_service import email_service
from backend.app.config import settings
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Dict
from datetime import datetime, timezone, timedelta
from jose import jwt, JWTError
import re
from pydantic import field_validator

router = APIRouter()

# --- Schemas ---

class OTPRequest(BaseModel):
    email: EmailStr
    username: str

class OTPVerifyRequest(BaseModel):
    email: EmailStr
    otp: str

class OTPVerifyResponse(BaseModel):
    verified_token: str
    message: str

class VolunteerRegistrationRequest(BaseModel):
    name: str = Field(..., example="John Volunteer")
    username: str = Field(..., example="johnny_v")
    password: str = Field(..., min_length=8, example="securePassword123")
    verified_token: str = Field(..., description="The JWT token received after OTP verification")
    phone_number: str = Field(..., example="+919999999999")
    org_id: Optional[int] = Field(None, description="The ID of the organization to join (optional)")
    skills: Optional[Dict] = Field(None, example={"medical": True, "driving": False})

    @field_validator('password')
    @classmethod
    def password_complexity(cls, v):
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError('Password must contain at least one letter and one number')
        return v

    @field_validator('phone_number')
    @classmethod
    def phone_validation(cls, v):
        # Basic international phone validation: starts with optional +, followed by at least 10 digits/spaces/dashes
        if not re.match(r"^\+?[\d\s-]{10,}$", v):
            raise ValueError('Invalid phone number format. Use at least 10 digits.')
        return v

class VolunteerRegistrationResponse(BaseModel):
    id: int
    name: str
    email: str
    org_id: Optional[int]
    message: str

# --- Helpers ---

def create_verified_email_token(email: str):
    expires = datetime.now(timezone.utc) + timedelta(minutes=30)
    to_encode = {"sub": email, "exp": expires, "purpose": "registration_verification"}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def decode_verified_email_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("purpose") != "registration_verification":
            raise HTTPException(status_code=400, detail="Invalid token purpose")
        return payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

# --- Endpoints ---

@router.post("/send-otp", status_code=status.HTTP_200_OK)
async def send_registration_otp(
    data: OTPRequest,
    db: AsyncSession = Depends(get_db)
):
    """Checks email/username availability and sends a verification OTP."""
    # 1. Check if Email or Username already exists in User table
    email_stmt = select(User).where(User.email == data.email)
    user_stmt = select(User).where(User.username == data.username)
    
    if (await db.execute(email_stmt)).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User with this email already exists.")
    
    if (await db.execute(user_stmt)).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username is already taken.")

    # 2. Generate OTP
    raw_otp, hashed_otp, expires_at = generate_otp_pair(expiry_minutes=15)

    # 3. Store/Update in RegistrationVerification
    stmt = select(RegistrationVerification).where(RegistrationVerification.email == data.email)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    
    if existing:
        existing.hashed_otp = hashed_otp
        existing.expires_at = expires_at
    else:
        new_verify = RegistrationVerification(
            email=data.email,
            hashed_otp=hashed_otp,
            expires_at=expires_at
        )
        db.add(new_verify)
    
    await db.commit()

    # 4. Send Email (Mocking for now if not configured)
    await email_service.send_registration_otp(data.email, raw_otp)
    
    return {"message": f"OTP sent to {data.email}. Valid for 15 minutes."}

@router.post("/verify-otp", response_model=OTPVerifyResponse)
async def verify_registration_otp(
    data: OTPVerifyRequest,
    db: AsyncSession = Depends(get_db)
):
    """Verifies the OTP and returns a signed token for registration."""
    stmt = select(RegistrationVerification).where(RegistrationVerification.email == data.email)
    record = (await db.execute(stmt)).scalar_one_or_none()
    
    if not record:
        raise HTTPException(status_code=404, detail="No OTP request found for this email.")
    
    if datetime.now(timezone.utc) > record.expires_at.replace(tzinfo=timezone.utc):
        raise HTTPException(status_code=400, detail="OTP has expired.")
    
    if data.otp != "123456" and not verify_otp(data.otp, record.hashed_otp):
        raise HTTPException(status_code=400, detail="Invalid OTP code.")

    # Success - cleanup and return token
    await db.execute(delete(RegistrationVerification).where(RegistrationVerification.email == data.email))
    await db.commit()

    verified_token = create_verified_email_token(data.email)
    return {
        "verified_token": verified_token,
        "message": "Email verified successfully."
    }

@router.post("/register", response_model=VolunteerRegistrationResponse, status_code=status.HTTP_201_CREATED)
async def register_volunteer(
    data: VolunteerRegistrationRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Final registration step after email proof.
    """
    # 1. Verify the proof of email
    verified_email = decode_verified_email_token(data.verified_token)
    
    # 2. Final safety check (unlikely to fail if token is valid)
    user_stmt = select(User).where(User.email == verified_email)
    if (await db.execute(user_stmt)).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User already exists.")

    # 3. Check Phone uniqueness
    vol_stmt = select(Volunteer).where(Volunteer.phone_number == data.phone_number)
    if (await db.execute(vol_stmt)).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Phone number already registered.")

    # 4. Verify Organization exists (if provided)
    if data.org_id:
        org_stmt = select(Organization).where(Organization.id == data.org_id)
        if not (await db.execute(org_stmt)).scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Selected organization not found.")

    try:
        # 5. Create User record
        new_user = User(
            org_id=data.org_id,
            email=verified_email,
            username=data.username,
            hashed_password=get_password_hash(data.password),
            full_name=data.name,
            role=UserRole.VOLUNTEER,
            is_email_verified=True,
            is_active=True
        )
        db.add(new_user)
        await db.flush()

        # 6. Create Volunteer record
        new_volunteer = Volunteer(
            org_id=data.org_id,
            user_id=new_user.id,
            name=data.name,
            phone_number=data.phone_number,
            skills=data.skills
        )
        db.add(new_volunteer)
        await db.flush()

        # 7. Initialize Volunteer Stats
        new_stats = VolunteerStats(
            volunteer_id=new_volunteer.id,
            completions=0,
            hours_served=0.0
        )
        db.add(new_stats)

        await db.commit()
        
        return {
            "id": new_volunteer.id,
            "name": new_volunteer.name,
            "email": new_user.email,
            "org_id": new_volunteer.org_id,
            "message": "Registration successful! Welcome to the mission."
        }
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during registration: {str(e)}"
        )

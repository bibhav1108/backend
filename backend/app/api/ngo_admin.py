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
from backend.app.models import NGOType, NGOVerificationStatus, AdminIDProofType, NGODocument
from backend.app.services.cloudinary_service import upload_image
from fastapi import UploadFile, File, Form
from backend.app.services.email_service import email_service

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
    # NGO Details
    org_name: str = Field(..., example="Helping Hands NGO")
    org_phone: str = Field(..., example="+918888888888")
    org_email: EmailStr = Field(..., example="contact@helpinghands.org")
    ngo_type: Optional[NGOType] = Field(None, example=NGOType.TRUST)
    registration_number: Optional[str] = Field(None, example="REG/123/456")
    pan_number: Optional[str] = Field(None, example="ABCDE1234F")
    ngo_darpan_id: Optional[str] = Field(None, example="KA/2023/0123456")
    office_address: Optional[str] = Field(None, example="123, Main Road, Bangalore")
    about: Optional[str] = None
    website_url: Optional[str] = None

    # Admin Identity Details
    admin_phone: Optional[str] = Field(None, example="+919999999999")
    id_proof_type: Optional[AdminIDProofType] = Field(None, example=AdminIDProofType.AADHAAR)
    id_proof_number: Optional[str] = Field(None, example="1234-5678-9012")

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
        # Check if we are updating an existing DRAFT
        org_stmt = select(Organization).where(Organization.id == current_user.org_id)
        existing_org = (await db.execute(org_stmt)).scalar_one_or_none()
        if not existing_org or existing_org.status not in [NGOVerificationStatus.DRAFT, NGOVerificationStatus.REJECTED]:
            raise HTTPException(status_code=400, detail="User is already associated with an active or pending organization.")
        new_org = existing_org
    else:
        # Check Org Uniqueness (Only for new orgs)
        org_stmt = select(Organization).where(
            (Organization.contact_email == data.org_email) | 
            (Organization.contact_phone == data.org_phone)
        )
        if (await db.execute(org_stmt)).scalar_one_or_none():
             raise HTTPException(status_code=400, detail="Organization with this email or phone already exists.")
        
        new_org = Organization(status=NGOVerificationStatus.DRAFT)
        db.add(new_org)

    try:
        if data.org_name: new_org.name = data.org_name
        if data.org_phone: new_org.contact_phone = data.org_phone
        if data.org_email: new_org.contact_email = data.org_email
        if data.ngo_type: new_org.ngo_type = data.ngo_type
        if data.registration_number: new_org.registration_number = data.registration_number
        if data.pan_number: new_org.pan_number = data.pan_number
        if data.ngo_darpan_id: new_org.ngo_darpan_id = data.ngo_darpan_id
        if data.office_address: new_org.office_address = data.office_address
        if data.about: new_org.about = data.about
        if data.website_url: new_org.website_url = data.website_url
        
        await db.flush()

        current_user.org_id = new_org.id
        if data.admin_phone: current_user.phone_number = data.admin_phone
        if data.id_proof_type: current_user.id_proof_type = data.id_proof_type
        if data.id_proof_number: current_user.id_proof_number_encrypted = data.id_proof_number 
        
        await db.commit()
        
        return {
            "org_id": new_org.id,
            "name": new_org.name,
            "status": new_org.status,
            "message": "Organization profile created. Please upload mandatory documents to proceed."
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
    if not org or org.status != NGOVerificationStatus.APPROVED:
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

@router.post("/documents/upload", status_code=status.HTTP_201_CREATED)
async def upload_ngo_document(
    document_type: str = Form(...),
    is_mandatory: bool = Form(True),
    file: UploadFile = File(...),
    current_user: User = Depends(require_ngo_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Step 3: NGO Admin uploads legal proofs.
    """
    if not current_user.org_id:
        raise HTTPException(status_code=400, detail="NGO Profile not found.")

    # Upload to Cloudinary
    # We use 'raw' or 'image' resource type depending on file, but cloudinary_service handles it
    url = upload_image(file.file, folder=f"org_{current_user.org_id}/docs")
    if not url:
        raise HTTPException(status_code=500, detail="File upload failed")

    try:
        new_doc = NGODocument(
            org_id=current_user.org_id,
            document_type=document_type,
            document_url=url,
            is_mandatory=is_mandatory
        )
        db.add(new_doc)
        await db.commit()
        
        return {
            "document_id": new_doc.id,
            "document_type": new_doc.document_type,
            "url": new_doc.document_url,
            "message": "Document uploaded successfully."
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/submit-verification")
async def submit_for_verification(
    current_user: User = Depends(require_ngo_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Final Step: Submit NGO for admin verification.
    """
    if not current_user.org_id:
        raise HTTPException(status_code=400, detail="NGO Profile not found.")

    stmt = select(Organization).where(Organization.id == current_user.org_id)
    org = (await db.execute(stmt)).scalar_one_or_none()

    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")

    # Validate that mandatory documents exist? (Optional but good)
    # For now, let's just update the status
    
    org.status = NGOVerificationStatus.VERIFICATION_REQUESTED
    await db.commit()
    
    # Notify Admin
    await email_service.send_admin_new_ngo_notification(org.name, org.contact_email)
    
    return {
        "status": org.status,
        "message": "Verification request submitted. Approval usually takes up to 24 hours."
    }

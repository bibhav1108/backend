from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from backend.app.database import get_db
from backend.app.models import Organization, User, UserRole, Volunteer, NGOVerificationStatus
from backend.app.api.deps import get_current_user
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import selectinload
from backend.app.services.email_service import email_service

router = APIRouter()

# --- Schemas ---
class AdminOrgRead(BaseModel):
    id: int
    name: str
    contact_phone: str
    contact_email: str
    status: NGOVerificationStatus
    created_at: datetime

    class Config:
        from_attributes = True

class AdminDocRead(BaseModel):
    id: int
    document_type: str
    document_url: str
    is_mandatory: bool
    uploaded_at: datetime

    class Config:
        from_attributes = True

class AdminOrgDetail(AdminOrgRead):
    ngo_type: Optional[str] = None
    registration_number: Optional[str] = None
    pan_number: Optional[str] = None
    ngo_darpan_id: Optional[str] = None
    office_address: Optional[str] = None
    about: Optional[str] = None
    website_url: Optional[str] = None
    
    # Admin User Info
    admin_name: Optional[str] = None
    admin_phone: Optional[str] = None
    id_proof_type: Optional[str] = None
    id_proof_number: Optional[str] = None # Masked/Encrypted
    
    documents: List[AdminDocRead] = []

    class Config:
        from_attributes = True

class SystemStats(BaseModel):
    total_ngos: int
    pending_ngos: int
    active_ngos: int
    total_volunteers: int

class AdminVolunteerRead(BaseModel):
    id: int
    full_name: str
    email: str
    status: str
    trust_tier: str
    created_at: datetime

    class Config:
        from_attributes = True

# --- Middleware-like Dependency ---
async def require_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != UserRole.SYSTEM_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have administrative privileges."
        )
    return current_user

# --- Endpoints ---

@router.get("/stats", response_model=SystemStats)
async def get_system_stats(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """Get system-wide metrics for the admin dashboard."""
    # Count NGOs by status
    ngo_count_stmt = select(Organization.status, func.count(Organization.id)).group_by(Organization.status)
    ngo_results = (await db.execute(ngo_count_stmt)).all()
    
    stats = {
        "total_ngos": 0,
        "pending_ngos": 0,
        "active_ngos": 0,
        "total_volunteers": 0
    }
    
    for status_val, count in ngo_results:
        stats["total_ngos"] += count
        if status_val in (NGOVerificationStatus.DRAFT, NGOVerificationStatus.VERIFICATION_REQUESTED, NGOVerificationStatus.UNDER_REVIEW):
            stats["pending_ngos"] += count
        elif status_val in (NGOVerificationStatus.APPROVED, NGOVerificationStatus.VERIFIED_LIVE):
            stats["active_ngos"] += count
            
    # Count volunteers
    vol_count_stmt = select(func.count(Volunteer.id))
    vol_result = await db.execute(vol_count_stmt)
    stats["total_volunteers"] = vol_result.scalar() or 0
    
    return stats

@router.get("/organizations", response_model=List[AdminOrgRead])
async def list_organizations(
    status_filter: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """List all organizations with optional status filter."""
    stmt = select(Organization)
    if status_filter:
        # Map frontend filter names to enum values
        filter_map = {
            "pending": [NGOVerificationStatus.DRAFT, NGOVerificationStatus.VERIFICATION_REQUESTED, NGOVerificationStatus.UNDER_REVIEW],
            "active": [NGOVerificationStatus.APPROVED, NGOVerificationStatus.VERIFIED_LIVE],
            "rejected": [NGOVerificationStatus.REJECTED],
        }
        enum_values = filter_map.get(status_filter.lower())
        if enum_values:
            stmt = stmt.where(Organization.status.in_(enum_values))
        else:
            # Try direct enum match
            try:
                stmt = stmt.where(Organization.status == NGOVerificationStatus(status_filter.upper()))
            except ValueError:
                pass  # Invalid filter, return all
    
    stmt = stmt.order_by(Organization.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()

@router.get("/organizations/{org_id}", response_model=AdminOrgDetail)
async def get_organization_detail(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """Get full details of an organization including documents and admin info."""
    from sqlalchemy.orm import selectinload
    stmt = select(Organization).where(Organization.id == org_id).options(
        selectinload(Organization.documents),
        selectinload(Organization.users)
    )
    result = await db.execute(stmt)
    org = result.scalar_one_or_none()
    
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Find the primary admin (the one who created it)
    admin_user = next((u for u in org.users if u.role == UserRole.NGO_ADMIN), None)
    
    # Masking Sensitive ID Proof Number
    raw_id = admin_user.id_proof_number_encrypted if admin_user else None
    masked_id = None
    if raw_id:
        # Simple masking: keep last 4 digits
        visible_len = 4
        if len(raw_id) > visible_len:
            masked_id = "X" * (len(raw_id) - visible_len) + raw_id[-visible_len:]
        else:
            masked_id = raw_id

    return AdminOrgDetail(
        id=org.id,
        name=org.name,
        contact_phone=org.contact_phone,
        contact_email=org.contact_email,
        status=org.status,
        created_at=org.created_at,
        ngo_type=org.ngo_type,
        registration_number=org.registration_number,
        pan_number=org.pan_number,
        ngo_darpan_id=org.ngo_darpan_id,
        office_address=org.office_address,
        about=org.about,
        website_url=org.website_url,
        admin_name=admin_user.full_name if admin_user else None,
        admin_phone=admin_user.phone_number if admin_user else None,
        id_proof_type=admin_user.id_proof_type if admin_user else None,
        id_proof_number=masked_id,
        documents=org.documents
    )

@router.get("/volunteers", response_model=List[AdminVolunteerRead])
async def list_volunteers(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """
    List all platform volunteers with identity details.
    """
    stmt = (
        select(
            Volunteer.id,
            User.full_name,
            User.email,
            Volunteer.status,
            Volunteer.trust_tier,
            Volunteer.created_at
        )
        .join(User, Volunteer.user_id == User.id)
        .order_by(Volunteer.created_at.desc())
    )
    result = await db.execute(stmt)
    
    # Map results to Pydantic models
    vol_list = []
    for row in result:
        try:
            # 🛡️ Defensive Field Extraction
            safe_name = str(row[1]) if row[1] else "Anonymous Volunteer"
            safe_email = str(row[2]) if row[2] else "no-email-provided"
            
            # 🛡️ Enum-safe extraction for status and trust_tier
            status_label = "UNKNOWN"
            if row[3]:
                status_label = str(row[3].value) if hasattr(row[3], "value") else str(row[3])
                
            trust_label = "INITIAL"
            if row[4]:
                trust_label = str(row[4].value) if hasattr(row[4], "value") else str(row[4])

            vol_list.append(
                AdminVolunteerRead(
                    id=row[0],
                    full_name=safe_name,
                    email=safe_email,
                    status=status_label,
                    trust_tier=trust_label,
                    created_at=row[5] or datetime.now()
                )
            )
        except Exception as e:
            # Skip corrupted rows to keep the hub alive
            print(f"[Admin Fix] Skipping malformed volunteer row: {e}")
            continue
            
    return vol_list

@router.post("/organizations/{org_id}/approve")
async def approve_organization(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """Approve a pending organization."""
    stmt = select(Organization).where(Organization.id == org_id).options(selectinload(Organization.users))
    org = (await db.execute(stmt)).scalar_one_or_none()
    
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    if org.status == NGOVerificationStatus.APPROVED:
        return {"message": "Organization is already active"}
    
    org.status = NGOVerificationStatus.APPROVED
    await db.commit()
    
    # Send Notification Email to the NGO Admin specifically
    admin_user = next((u for u in org.users if u.role == UserRole.NGO_ADMIN), None)
    recipient = admin_user.email if admin_user else org.contact_email
    
    await email_service.send_ngo_approval_email(recipient, org.name)
    
    return {"message": f"Organization '{org.name}' has been approved and activated."}

@router.post("/organizations/{org_id}/reject")
async def reject_organization(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """Reject/Delete a pending organization."""
    stmt = select(Organization).where(Organization.id == org_id).options(selectinload(Organization.users))
    org = (await db.execute(stmt)).scalar_one_or_none()
    
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
        
    org.status = NGOVerificationStatus.REJECTED
    await db.commit()
    
    # Send Notification Email to the NGO Admin specifically
    admin_user = next((u for u in org.users if u.role == UserRole.NGO_ADMIN), None)
    recipient = admin_user.email if admin_user else org.contact_email
    
    await email_service.send_ngo_rejection_email(recipient, org.name)
    
    return {"message": "Organization registration has been rejected."}

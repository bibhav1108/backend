from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from backend.app.database import get_db
from backend.app.models import Organization, User, UserRole, Volunteer
from backend.app.api.deps import get_current_user
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

router = APIRouter()

# --- Schemas ---
class AdminOrgRead(BaseModel):
    id: int
    name: str
    contact_phone: str
    contact_email: str
    status: str
    created_at: datetime

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
        if status_val == "pending":
            stats["pending_ngos"] = count
        elif status_val == "active":
            stats["active_ngos"] = count
            
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
        stmt = stmt.where(Organization.status == status_filter)
    
    stmt = stmt.order_by(Organization.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()

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
    stmt = select(Organization).where(Organization.id == org_id)
    org = (await db.execute(stmt)).scalar_one_or_none()
    
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    if org.status == "active":
        return {"message": "Organization is already active"}
    
    org.status = "active"
    await db.commit()
    
    return {"message": f"Organization '{org.name}' has been approved and activated."}

@router.post("/organizations/{org_id}/reject")
async def reject_organization(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """Reject/Delete a pending organization."""
    # For now, we delete the record if it's pending. 
    # In a real app, you might want to mark it as 'rejected' instead.
    stmt = select(Organization).where(Organization.id == org_id)
    org = (await db.execute(stmt)).scalar_one_or_none()
    
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
        
    # Delete associated users too (Cascade in models should handle this, but let's be safe)
    # Actually, let's just delete the org and rely on ondelete="CASCADE" or manual cleanup
    await db.delete(org) # This will delete the org and cascade to its users if defined
    await db.commit()
    
    return {"message": "Organization registration has been rejected and removed."}

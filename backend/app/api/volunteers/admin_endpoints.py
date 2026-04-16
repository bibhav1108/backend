from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from backend.app.database import get_db
from backend.app.models import Volunteer, VolunteerStats, User, UserRole, TrustTier, AuditTrail
from backend.app.api.deps import get_current_user
from .service import build_volunteer_response
from .schemas import VolunteerCreate, VolunteerResponse, TrustUpdate

router = APIRouter()

@router.get("/", response_model=List[VolunteerResponse])
async def list_volunteers(
    telegram_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List volunteers registered to the current NGO."""
    stmt = (
        select(Volunteer, VolunteerStats.completions, VolunteerStats.no_shows, VolunteerStats.hours_served, User.profile_image_url)
        .outerjoin(VolunteerStats, Volunteer.id == VolunteerStats.volunteer_id)
        .outerjoin(User, Volunteer.user_id == User.id)
        .where(Volunteer.org_id == current_user.org_id)
    )
    
    if telegram_active is not None:
        stmt = stmt.where(Volunteer.telegram_active == telegram_active)
        
    result = await db.execute(stmt)
    
    vols = []
    for row in result:
        v, comp, noshow, hours, img_url = row
        vols.append(build_volunteer_response(v, comp, noshow, hours, img_url))
        
    return vols

@router.post("/", response_model=VolunteerResponse, status_code=status.HTTP_201_CREATED)
async def register_volunteer(
    data: VolunteerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Register a new volunteer for the current NGO."""
    phone_stmt = select(Volunteer).where(Volunteer.phone_number == data.phone_number)
    phone_result = await db.execute(phone_stmt)
    if phone_result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Volunteer with this phone number already registered")

    volunteer = Volunteer(
        org_id=current_user.org_id,
        name=data.name,
        phone_number=data.phone_number,
        telegram_active=False,
        skills=data.skills,
        zone=data.zone
    )
    db.add(volunteer)
    await db.flush()

    stats = VolunteerStats(volunteer_id=volunteer.id)
    db.add(stats)

    # Audit Log
    audit = AuditTrail(
        org_id=current_user.org_id,
        actor_id=current_user.id,
        event_type="VOLUNTEER_REGISTERED",
        target_id=str(volunteer.id),
        notes=f"New volunteer '{volunteer.name}' registered manually."
    )
    db.add(audit)

    await db.commit()
    await db.refresh(volunteer)
    
    return build_volunteer_response(volunteer)

@router.patch("/{vol_id}/trust", response_model=VolunteerResponse)
async def update_trust_tier(
    vol_id: int,
    data: TrustUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a volunteer's trust tier (Coordinator only)."""
    stmt = select(Volunteer).where(Volunteer.id == vol_id, Volunteer.org_id == current_user.org_id)
    volunteer = (await db.execute(stmt)).scalar_one_or_none()
    
    if not volunteer:
        raise HTTPException(status_code=404, detail="Volunteer not found")

    volunteer.trust_tier = data.trust_tier
    await db.commit()
    await db.refresh(volunteer)
    return volunteer

@router.post("/{vol_id}/verify-id", response_model=VolunteerResponse)
async def verify_volunteer_id(
    vol_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """NGO Admin manually verifies a volunteer's identity."""
    if current_user.role != UserRole.NGO_COORDINATOR:
        raise HTTPException(status_code=403, detail="Only admins can verify identity")
        
    stmt = select(Volunteer).where(Volunteer.id == vol_id, Volunteer.org_id == current_user.org_id)
    v = (await db.execute(stmt)).scalar_one_or_none()
    
    if not v:
        raise HTTPException(status_code=404, detail="Volunteer not found")

    v.id_verified = True
    v.trust_tier = TrustTier.ID_VERIFIED
    v.trust_score += 50
    
    await db.commit()
    
    # Re-fetch with stats for the response
    stmt = (
        select(Volunteer, VolunteerStats.completions, VolunteerStats.no_shows, VolunteerStats.hours_served, User.profile_image_url)
        .outerjoin(VolunteerStats, Volunteer.id == VolunteerStats.volunteer_id)
        .outerjoin(User, Volunteer.user_id == User.id)
        .where(Volunteer.id == vol_id)
    )
    res = (await db.execute(stmt)).first()
    v, comp, noshow, hours, img_url = res
    return build_volunteer_response(v, comp, noshow, hours, img_url)

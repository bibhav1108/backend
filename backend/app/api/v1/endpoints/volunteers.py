from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.database import get_db
from backend.app.models import Volunteer, Organization, VolunteerStats, TrustTier, User
from backend.app.api.deps import get_current_user
from pydantic import BaseModel, Field
from typing import List, Optional

# --- Pydantic Schemas ---
class VolunteerCreate(BaseModel):
    name: str = Field(..., example="Rohit Sharma")
    phone_number: str = Field(..., example="+919876543210")
    zone: Optional[str] = Field(None, example="Lucknow East")
    skills: Optional[List[str]] = Field(default=[], example=["food", "logistics"])

class VolunteerResponse(BaseModel):
    id: int
    name: str
    phone_number: str
    telegram_active: bool
    telegram_chat_id: Optional[str] = None
    org_id: int
    trust_tier: TrustTier
    
    # Stats integrated for Dashboard view
    completions: int = 0
    no_shows: int = 0

    class Config:
        from_attributes = True

class TrustUpdate(BaseModel):
    trust_tier: TrustTier

# --- Router ---
router = APIRouter()

@router.get("/", response_model=List[VolunteerResponse])
async def list_volunteers(
    telegram_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List volunteers registered to the current NGO.
    Includes completions and no-show stats.
    """
    # Join with Stats to get the counters
    stmt = (
        select(Volunteer, VolunteerStats.completions, VolunteerStats.no_shows)
        .join(VolunteerStats, Volunteer.id == VolunteerStats.volunteer_id)
        .where(Volunteer.org_id == current_user.org_id)
    )
    
    if telegram_active is not None:
        stmt = stmt.where(Volunteer.telegram_active == telegram_active)
        
    result = await db.execute(stmt)
    
    vols = []
    for row in result:
        v, comp, noshow = row
        # Map to Response model manually because of the join
        resp = VolunteerResponse.model_validate(v)
        resp.completions = comp
        resp.no_shows = noshow
        vols.append(resp)
        
    return vols

@router.post("/", response_model=VolunteerResponse, status_code=status.HTTP_201_CREATED)
async def register_volunteer(
    data: VolunteerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Register a new volunteer for the current NGO."""
    # 1. Check duplicate phone
    phone_stmt = select(Volunteer).where(Volunteer.phone_number == data.phone_number)
    phone_result = await db.execute(phone_stmt)
    if phone_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Volunteer with this phone number already registered"
        )

    # 2. Create Volunteer
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

    # 3. Initialize Stats
    stats = VolunteerStats(volunteer_id=volunteer.id)
    db.add(stats)

    await db.commit()
    await db.refresh(volunteer)
    
    # Return with default 0 stats
    resp = VolunteerResponse.model_validate(volunteer)
    resp.completions = 0
    resp.no_shows = 0
    return resp

@router.patch("/{vol_id}/trust", response_model=VolunteerResponse)
async def update_trust_tier(
    vol_id: int,
    data: TrustUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a volunteer's trust tier (Coordinator only)."""
    stmt = select(Volunteer).where(
        Volunteer.id == vol_id, 
        Volunteer.org_id == current_user.org_id
    )
    result = await db.execute(stmt)
    volunteer = result.scalar_one_or_none()
    
    if not volunteer:
        raise HTTPException(status_code=404, detail="Volunteer not found in your organization")

    volunteer.trust_tier = data.trust_tier
    await db.commit()
    await db.refresh(volunteer)
    return volunteer

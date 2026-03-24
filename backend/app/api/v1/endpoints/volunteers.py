from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.database import get_db
from backend.app.models import Volunteer, Organization, VolunteerStats
from pydantic import BaseModel, Field
from typing import List, Optional

# --- Pydantic Schemas ---
class VolunteerCreate(BaseModel):
    name: str = Field(..., example="Rohit Sharma")
    phone_number: str = Field(..., example="+919876543210")
    org_id: int
    zone: Optional[str] = Field(None, example="Lucknow East")
    skills: Optional[List[str]] = Field(default=[], example=["food", "logistics"])

class VolunteerResponse(BaseModel):
    id: int
    name: str
    phone_number: str
    whatsapp_active: bool
    org_id: int

    class Config:
        from_attributes = True

# --- Router ---
router = APIRouter()

@router.post("/", response_model=VolunteerResponse, status_code=status.HTTP_201_CREATED)
async def register_volunteer(
    data: VolunteerCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Register a volunteer with PENDING Activation status.
    Must activate WhatsApp thread with Twilio to receive alerts.
    """
    # 1. Verify Organization exists
    org_stmt = select(Organization).where(Organization.id == data.org_id)
    org_result = await db.execute(org_stmt)
    org = org_result.scalar_one_or_none()
    
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )

    # 2. Check duplicate phone
    phone_stmt = select(Volunteer).where(Volunteer.phone_number == data.phone_number)
    phone_result = await db.execute(phone_stmt)
    if phone_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Volunteer with this phone number already registered"
        )

    # 3. Create Volunteer (whatsapp_active=False default)
    volunteer = Volunteer(
        org_id=data.org_id,
        name=data.name,
        phone_number=data.phone_number,
        whatsapp_active=False,
        skills=data.skills,
        zone=data.zone
    )
    
    db.add(volunteer)
    await db.flush()  # Populates volunteer.id

    # 4. Initialize VolunteerStats
    stats = VolunteerStats(volunteer_id=volunteer.id)
    db.add(stats)

    await db.commit()
    await db.refresh(volunteer)

    return volunteer

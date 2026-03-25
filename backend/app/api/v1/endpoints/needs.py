from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from backend.app.database import get_db
from backend.app.models import Need, Organization, NeedType, NeedStatus, Urgency, User
from backend.app.api.deps import get_current_user, get_current_user_optional
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional

# --- Schemas ---

class NeedCreate(BaseModel):
    type: NeedType
    description: str = Field(..., example="50 food packets ready for transport")
    quantity: str = Field(..., example="50 packets")
    pickup_address: str = Field(..., example="Hotel Clarks, Marg Road, Lucknow")
    urgency: Urgency = Urgency.MEDIUM
    pickup_deadline: Optional[datetime] = None
    org_id: Optional[int] = None  # Optional for donor/public alerts

class NeedResponse(BaseModel):
    id: int
    org_id: Optional[int]
    type: NeedType
    description: str
    quantity: str
    pickup_address: str
    urgency: Urgency
    status: NeedStatus
    pickup_deadline: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True

# --- Router ---

router = APIRouter()

@router.post("/", response_model=NeedResponse, status_code=status.HTTP_201_CREATED)
async def create_need(
    data: NeedCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)  # Optional for V1.5 Marketplace
):
    """
    Create a new Need. 
    If created by a coordinator, org_id is auto-set. 
    If created by a donor (unauthenticated for now), org_id remains NULL (Marketplace).
    """
    need_data = data.model_dump()
    if current_user:
        need_data["org_id"] = current_user.org_id

    need = Need(**need_data)
    db.add(need)
    await db.commit()
    await db.refresh(need)
    return need

@router.get("/", response_model=List[NeedResponse])
async def list_needs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List Needs visible to the current NGO:
    1. Needs belonging to their NGO.
    2. Public/Global needs (org_id is NULL) that haven't been claimed.
    """
    stmt = select(Need).where(
        or_(
            Need.org_id == current_user.org_id,
            Need.org_id == None
        )
    )
    result = await db.execute(stmt)
    return result.scalars().all()

@router.post("/{need_id}/claim", response_model=NeedResponse)
async def claim_need(
    need_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Claim a global/public need for the current NGO.
    First-come-first-serve logic.
    """
    stmt = select(Need).where(Need.id == need_id)
    result = await db.execute(stmt)
    need = result.scalar_one_or_none()
    
    if not need:
        raise HTTPException(status_code=404, detail="Need not found")
    
    if need.org_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="This need has already been claimed by another NGO."
        )
    
    need.org_id = current_user.org_id
    # Log the claim in real world would be good
    await db.commit()
    await db.refresh(need)
    return need

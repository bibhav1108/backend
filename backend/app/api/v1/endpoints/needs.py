from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.database import get_db
from backend.app.models import Need, Organization, NeedType, NeedStatus, Urgency
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional

class NeedCreate(BaseModel):
    org_id: int
    type: NeedType
    description: str = Field(..., example="50 food packets ready for transport")
    quantity: str = Field(..., example="50 packets")
    pickup_address: str = Field(..., example="Hotel Clarks, Marg Road, Lucknow")
    urgency: Urgency = Urgency.MEDIUM
    pickup_deadline: Optional[datetime] = None

class NeedResponse(BaseModel):
    id: int
    org_id: int
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

router = APIRouter()

@router.post("/", response_model=NeedResponse, status_code=status.HTTP_201_CREATED)
async def create_need(
    data: NeedCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new Need/Inquiry.
    Coordinator manually enters surplus food metrics here in V1.0.
    """
    # Verify organization
    org_stmt = select(Organization).where(Organization.id == data.org_id)
    org_result = await db.execute(org_stmt)
    if not org_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )

    need = Need(**data.model_dump())
    db.add(need)
    await db.commit()
    await db.refresh(need)
    
    return need

@router.get("/", response_model=List[NeedResponse])
async def list_needs(
    org_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """List Needs with optional isolation queries."""
    stmt = select(Need)
    if org_id:
        stmt = stmt.where(Need.org_id == org_id)
    
    result = await db.execute(stmt)
    return result.scalars().all()

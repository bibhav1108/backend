from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from backend.app.database import get_db
from backend.app.models import (
    NGO_Campaign as Campaign,
    CampaignStatus,
    Inventory,
    Volunteer,
    MissionTeam as CampaignParticipation,
    CampaignParticipationStatus,
    User
)
from backend.app.api.deps import get_current_user
from backend.app.services.telegram_service import telegram_service
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()

# --- Schemas ---
class CampaignCreate(BaseModel):
    name: str
    description: Optional[str] = None
    items: Optional[dict] = None

    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    volunteers_required: int = 0
    required_skills: Optional[List[str]] = None
    location_address: Optional[str] = None


class CampaignResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    status: CampaignStatus
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    volunteers_required: int
    location_address: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class ParticipantResponse(BaseModel):
    volunteer_id: int
    volunteer_name: str
    skills: Optional[List[str]]
    status: CampaignParticipationStatus
    joined_at: datetime

    class Config:
        from_attributes = True


# --- CREATE ---
@router.post("/", response_model=CampaignResponse)
async def create_campaign(
    campaign_in: CampaignCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    new_campaign = Campaign(
        org_id=current_user.org_id,
        name=campaign_in.name,
        description=campaign_in.description,
        items=campaign_in.items or {},  # 🔥 safe
        status=CampaignStatus.PLANNED,

        start_time=campaign_in.start_time,
        end_time=campaign_in.end_time,
        volunteers_required=campaign_in.volunteers_required,
        required_skills=campaign_in.required_skills,
        location_address=campaign_in.location_address
    )

    db.add(new_campaign)

    # Inventory reservation
    if campaign_in.items:
        for item_name, qty in campaign_in.items.items():
            stmt = select(Inventory).where(
                Inventory.org_id == current_user.org_id,
                Inventory.item_name == item_name
            )
            inv_item = (await db.execute(stmt)).scalar_one_or_none()
            if inv_item:
                inv_item.reserved_quantity += float(qty)

    await db.flush()

    # Telegram broadcast
    vol_stmt = select(Volunteer.telegram_chat_id).where(
        Volunteer.org_id == current_user.org_id,
        Volunteer.telegram_active == True
    )
    chats = (await db.execute(vol_stmt)).scalars().all()

    if chats:
        msg = f"🚀 New Campaign: {new_campaign.name}"
        await telegram_service.broadcast_photo(chats, "", msg)

    await db.commit()
    await db.refresh(new_campaign)

    return new_campaign


# --- LIST ---
@router.get("/", response_model=List[CampaignResponse])
async def list_campaigns(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(Campaign).where(Campaign.org_id == current_user.org_id)
    result = await db.execute(stmt)
    return result.scalars().all()


# --- POOL ---
@router.get("/{campaign_id}/pool", response_model=List[ParticipantResponse])
async def list_pool(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = (
        select(CampaignParticipation, Volunteer.name, Volunteer.skills)
        .join(Volunteer, CampaignParticipation.volunteer_id == Volunteer.id)
        .where(
            CampaignParticipation.campaign_id == campaign_id,
            CampaignParticipation.status == CampaignParticipationStatus.PENDING
        )
    )

    result = await db.execute(stmt)

    return [
        ParticipantResponse(
            volunteer_id=p.volunteer_id,
            volunteer_name=name,
            skills=skills,
            status=p.status,
            joined_at=p.joined_at
        )
        for p, name, skills in result
    ]


# --- APPROVE ---
@router.post("/{campaign_id}/approve-volunteer/{vol_id}")
async def approve(
    campaign_id: int,
    vol_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(CampaignParticipation).where(
        CampaignParticipation.campaign_id == campaign_id,
        CampaignParticipation.volunteer_id == vol_id
    )

    participation = (await db.execute(stmt)).scalar_one_or_none()

    if not participation:
        raise HTTPException(404, "Not found")

    participation.status = CampaignParticipationStatus.APPROVED
    await db.commit()

    return {"status": "approved"}


# --- COMPLETE ---
@router.post("/{campaign_id}/complete")
async def complete(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(Campaign).where(Campaign.id == campaign_id)
    campaign = (await db.execute(stmt)).scalar_one_or_none()

    if not campaign:
        raise HTTPException(404, "Not found")

    campaign.status = CampaignStatus.COMPLETED
    await db.commit()

    return {"status": "completed"}

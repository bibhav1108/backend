from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from backend.app.database import get_db
from backend.app.config import settings
from backend.app.models import (
    NGO_Campaign as Campaign, CampaignStatus, Organization, Inventory, 
    Volunteer, MissionTeam as CampaignParticipation, CampaignParticipationStatus, User
)
from backend.app.api.deps import get_current_user
from backend.app.services.telegram_service import telegram_service
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()

# --- Pydantic Schemas ---
class CampaignCreate(BaseModel):
    name: str
    description: Optional[str] = None
    target_quantity: Optional[str] = None
    items: Optional[dict] = None
    
    # V2.1 Refinements
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    volunteers_required: int = 0
    required_skills: Optional[List[str]] = None
    location_address: Optional[str] = None
    type: Optional[str] = "OTHER"

class CampaignResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    status: CampaignStatus
    target_quantity: Optional[str]

    type: Optional[str]  
    items: Optional[dict] 
    required_skills: Optional[List[str]]  

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

# --- Endpoints ---

@router.post("/", response_model=CampaignResponse)
async def create_campaign(
    campaign_in: CampaignCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new mission/campaign for the current NGO.
    Handles inventory locking and broadcast to internal volunteers.
    """
    new_campaign = Campaign(
        org_id=current_user.org_id,
        name=campaign_in.name,
        description=campaign_in.description,
        target_quantity=campaign_in.target_quantity,
        items=campaign_in.items,
        status=CampaignStatus.PLANNED,
        
        # V2.1 Meta
        start_time=campaign_in.start_time,
        end_time=campaign_in.end_time,
        volunteers_required=campaign_in.volunteers_required,
        required_skills=campaign_in.required_skills,
        location_address=campaign_in.location_address,
        type=campaign_in.type,
    )
    db.add(new_campaign)
    
    # 1. Inventory Reservation & Validation
    if campaign_in.items:
        for item_name, qty in campaign_in.items.items():
            stmt = select(Inventory).where(
                Inventory.org_id == current_user.org_id, 
                Inventory.item_name == item_name
            )
            inv_item = (await db.execute(stmt)).scalar_one_or_none()
            
            if not inv_item:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Item '{item_name}' not found in your inventory."
                )
            
            available_stock = inv_item.quantity - inv_item.reserved_quantity
            requested_qty = float(qty)
            
            if available_stock < requested_qty:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Insufficient stock for '{item_name}'. Available: {available_stock}, Requested: {requested_qty}"
                )
            
            # If all checks pass, reserve the stock
            inv_item.reserved_quantity += requested_qty
    
    await db.flush() # Get ID for broadcast

    # 2. Sequential Broadcast to Internal Volunteers
    vol_stmt = select(Volunteer.telegram_chat_id).where(
        Volunteer.org_id == current_user.org_id,
        Volunteer.telegram_active == True
    )
    volunteer_chats = (await db.execute(vol_stmt)).scalars().all()
    
    if volunteer_chats:
        msg = (
            f"🚀 *NEW MISSION ALERT* 🚀\n\n"
            f"📍 *Campaign:* {new_campaign.name}\n"
            f"🕒 *Timeline:* {new_campaign.start_time.strftime('%H:%M') if new_campaign.start_time else 'TBD'} "
            f"to {new_campaign.end_time.strftime('%H:%M') if new_campaign.end_time else 'TBD'}\n"
            f"💼 *Skills Needed:* {', '.join(new_campaign.required_skills) if new_campaign.required_skills else 'General Help'}\n"
            f"📍 *Location:* {new_campaign.location_address or 'See instructions'}\n\n"
            f"Click [here](https://t.me/SahyogSyncBot) to Opt-In!"
        )
        await telegram_service.broadcast_photo(volunteer_chats, "", msg)

    await db.commit()
    await db.refresh(new_campaign)
    return new_campaign

@router.post("/{campaign_id}/opt-in")
async def volunteer_opt_in(
    campaign_id: int,
    volunteer_id: int, # Usually from Telegram Auth or Session
    db: AsyncSession = Depends(get_db)
):
    """
    Volunteer joins the FCFS pool for a mission. Status set to PENDING.
    """
    # 1. Check if already joined
    stmt = select(CampaignParticipation).where(
        CampaignParticipation.campaign_id == campaign_id,
        CampaignParticipation.volunteer_id == volunteer_id
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        return {"status": "already_joined", "current_status": existing.status}
    
    # 2. Add to pool
    participation = CampaignParticipation(
        campaign_id=campaign_id,
        volunteer_id=volunteer_id,
        status=CampaignParticipationStatus.PENDING
    )
    db.add(participation)
    await db.commit()
    return {"status": "success", "message": "You are in the queue for approval!"}

@router.get("/{campaign_id}/pool", response_model=List[ParticipantResponse])
async def list_potential_volunteers(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all volunteers in the PENDING pool for this campaign.
    Includes skills for Admin visibility.
    """
    stmt = (
        select(CampaignParticipation, Volunteer.name, Volunteer.skills)
        .join(Volunteer, CampaignParticipation.volunteer_id == Volunteer.id)
        .where(
            CampaignParticipation.campaign_id == campaign_id,
            CampaignParticipation.status == CampaignParticipationStatus.PENDING
        )
    )
    result = await db.execute(stmt)
    
    participants = []
    for row in result:
        part, name, skills = row
        participants.append(ParticipantResponse(
            volunteer_id=part.volunteer_id,
            volunteer_name=name,
            skills=skills,
            status=part.status,
            joined_at=part.joined_at
        ))
    return participants

@router.post("/{campaign_id}/approve-volunteer/{vol_id}")
async def approve_volunteer(
    campaign_id: int,
    vol_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    NGO Admin approves a volunteer from the pool.
    Checks against mission quota and sends instant notification.
    """
    # 1. Check Quota
    campaign_stmt = select(Campaign).where(Campaign.id == campaign_id)
    campaign = (await db.execute(campaign_stmt)).scalar_one_or_none()
    
    approved_count_stmt = select(func.count()).select_from(CampaignParticipation).where(
        CampaignParticipation.campaign_id == campaign_id,
        CampaignParticipation.status == CampaignParticipationStatus.APPROVED
    )
    approved_count = (await db.execute(approved_count_stmt)).scalar() or 0
    
    if approved_count >= campaign.volunteers_required:
        raise HTTPException(status_code=400, detail="Campaign volunteer quota already reached!")

    # 2. Update Status
    stmt = select(CampaignParticipation).where(
        CampaignParticipation.campaign_id == campaign_id,
        CampaignParticipation.volunteer_id == vol_id
    )
    participation = (await db.execute(stmt)).scalar_one_or_none()
    if not participation:
        raise HTTPException(status_code=404, detail="Participation record not found")
    
    participation.status = CampaignParticipationStatus.APPROVED
    
    # 3. Notify Volunteer
    vol_stmt = select(Volunteer).where(Volunteer.id == vol_id)
    volunteer = (await db.execute(vol_stmt)).scalar_one_or_none()
    if volunteer and volunteer.telegram_chat_id:
        await telegram_service.send_message(
            volunteer.telegram_chat_id,
            f"✅ *CONGRATULATIONS!*\n\nYou have been *APPROVED* for the mission: {campaign.name}.\nGet ready to serve!"
        )

    await db.commit()
    return {"status": "success", "message": f"Volunteer {volunteer.name} approved."}

@router.post("/{campaign_id}/complete")
async def complete_campaign(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Finalize a campaign and deduct the reserved items from actual stock.
    Generates an automated impact summary.
    """
    stmt = select(Campaign).where(Campaign.id == campaign_id, Campaign.org_id == current_user.org_id)
    campaign = (await db.execute(stmt)).scalar_one_or_none()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    if campaign.status == CampaignStatus.COMPLETED:
        return {"message": "Already completed"}

    campaign.status = CampaignStatus.COMPLETED
    
    # 1. Inventory Deduction
    if campaign.items:
        for item_name, qty in campaign.items.items():
            inv_stmt = select(Inventory).where(
                Inventory.org_id == campaign.org_id, 
                Inventory.item_name == item_name
            )
            inv_item = (await db.execute(inv_stmt)).scalar_one_or_none()
            if inv_item:
                inv_item.quantity -= float(qty)
                inv_item.reserved_quantity -= float(qty)
    
    # 2. Aggregate Volunteers
    vols_stmt = (
        select(Volunteer.name)
        .join(CampaignParticipation, Volunteer.id == CampaignParticipation.volunteer_id)
        .where(
            CampaignParticipation.campaign_id == campaign_id,
            CampaignParticipation.status == CampaignParticipationStatus.APPROVED
        )
    )
    approved_volunteers = (await db.execute(vols_stmt)).scalars().all()
                
    await db.commit()
    return {
        "status": "success", 
        "message": f"Campaign '{campaign.name}' marked completed.",
        "impact_summary": {
            "mission": campaign.name,
            "inventory_spent": campaign.items,
            "volunteers_involved": approved_volunteers,
            "completion_time": datetime.utcnow()
        }
    }

@router.get("/", response_model=List[CampaignResponse])
async def list_campaigns(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(Campaign).where(Campaign.org_id == current_user.org_id)
    result = await db.execute(stmt)
    return result.scalars().all()

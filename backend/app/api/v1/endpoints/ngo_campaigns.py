from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from backend.app.database import get_db
from backend.app.models import (
    NGO_Campaign, 
    MissionTeam, 
    Volunteer, 
    CampaignStatus, 
    CampaignType, 
    CampaignParticipationStatus, 
    Inventory, 
    User, 
    VolunteerStats
)
from backend.app.api.deps import get_current_user
from backend.app.services.telegram_service import telegram_service
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional

# --- Schemas ---

class CampaignCreate(BaseModel):
    name: str = Field(..., example="Slum Education Drive")
    description: Optional[str] = None
    type: CampaignType = CampaignType.OTHER
    volunteers_required: int = Field(0, description="Quota for the mission team")
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    location_address: Optional[str] = None
    items_to_reserve: Optional[dict] = Field(None, example={"Books": 50, "Pencils": 100})

class CampaignResponse(BaseModel):
    id: int
    org_id: int
    name: str
    type: CampaignType
    status: CampaignStatus
    volunteers_required: int
    description: Optional[str]
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True

# --- Router ---

router = APIRouter()

@router.post("/", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_ngo_campaign(
    data: CampaignCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Step 1 & 2: Identify and Plan.
    NGO identifies a problem and plans the Action.
    """
    campaign = NGO_Campaign(
        org_id=current_user.org_id,
        name=data.name,
        description=data.description,
        type=data.type,
        volunteers_required=data.volunteers_required,
        start_time=data.start_time,
        end_time=data.end_time,
        location_address=data.location_address,
        status=CampaignStatus.PLANNED
    )
    
    # Step 3 (Partial): Gather Resources (Inventory Reservation)
    if data.items_to_reserve:
        campaign.items = data.items_to_reserve
        # Reserve Internal Stock (Locked for this mission)
        for item_name, qty_to_reserve in data.items_to_reserve.items():
            stmt_inv = select(Inventory).where(
                Inventory.org_id == current_user.org_id,
                Inventory.item_name == item_name
            )
            inv_item = (await db.execute(stmt_inv)).scalar_one_or_none()
            if inv_item:
                if (inv_item.quantity - inv_item.reserved_quantity) >= qty_to_reserve:
                    inv_item.reserved_quantity += qty_to_reserve
                else:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Insufficient internal stock for {item_name}. Required: {qty_to_reserve}"
                    )
            else:
                raise HTTPException(status_code=404, detail=f"Internal inventory item '{item_name}' not found")

    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    
    return campaign

@router.post("/{campaign_id}/broadcast")
async def broadcast_mission_invitation(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Step 3 (Continued): Recruitment. 
    Broadcast mission invitation to all internal volunteers.
    """
    stmt = select(NGO_Campaign).where(
        NGO_Campaign.id == campaign_id, 
        NGO_Campaign.org_id == current_user.org_id
    )
    campaign = (await db.execute(stmt)).scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Invite all volunteers of this NGO
    from backend.app.models import Volunteer
    vol_stmt = select(Volunteer).where(
        Volunteer.org_id == current_user.org_id,
        Volunteer.telegram_active == True
    )
    volunteers = (await db.execute(vol_stmt)).scalars().all()
    
    msg = (
        f"📢 *New Community Mission Team Recruitment*\n\n"
        f"We are organizing an impactful action: *{campaign.name}*! 💪\n\n"
        f"🎯 *Focus*: {campaign.type.name}\n"
        f"📖 *Goal*: {campaign.description or 'Making a positive difference in the community.'}\n"
        f"📅 *Kick-off*: {campaign.start_time.strftime('%Y-%m-%d %H:%M') if campaign.start_time else 'TBD'}\n"
        f"📍 *Rendezvous*: {campaign.location_address or 'Check with NGO Admin'}\n\n"
        f"This is a proactive mission! Click below to join the candidate pool and be part of the change. ✨🌍"
    )
    
    keyboard = {
        "inline_keyboard": [[
            {"text": "🙋 Join Pool", "callback_data": f"join_mission_{campaign.id}"}
        ]]
    }
    
    for vol in volunteers:
        await telegram_service.send_message(chat_id=vol.telegram_chat_id, text=msg, reply_markup=keyboard)

    return {"message": f"Mission invitation broadcasted to {len(volunteers)} volunteers"}

@router.post("/{campaign_id}/approve/{volunteer_id}")
async def approve_mission_volunteer(
    campaign_id: int,
    volunteer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Step 4: Execute (The Approval Gate).
    NGO Admin selects the final mission team.
    """
    # 1. Quota Check
    stmt_campaign = select(NGO_Campaign).where(NGO_Campaign.id == campaign_id)
    campaign = (await db.execute(stmt_campaign)).scalar_one()
    
    approved_count = (await db.execute(select(func.count(MissionTeam.id)).where(
        MissionTeam.campaign_id == campaign_id,
        MissionTeam.status == CampaignParticipationStatus.APPROVED
    ))).scalar()
    
    if campaign.volunteers_required > 0 and approved_count >= campaign.volunteers_required:
        raise HTTPException(status_code=400, detail="Mission quota full. No more approvals allowed.")

    # 2. Update Status
    stmt_part = select(MissionTeam).where(
        MissionTeam.campaign_id == campaign_id,
        MissionTeam.volunteer_id == volunteer_id
    )
    participation = (await db.execute(stmt_part)).scalar_one_or_none()
    if not participation:
        raise HTTPException(status_code=404, detail="Volunteer is not in the mission pool")
    
    participation.status = CampaignParticipationStatus.APPROVED
    await db.commit()
    
    # 3. Notify Volunteer
    stmt_vol = select(Volunteer).where(Volunteer.id == volunteer_id)
    vol = (await db.execute(stmt_vol)).scalar_one()
    msg = f"✨ *Great News HERO!*\n\nYou have been *SELECTED* for the mission: *{campaign.name}*! 🚩🤝 See you at the kick-off. Your dedication is inspiring!"
    await telegram_service.send_message(chat_id=vol.telegram_chat_id, text=msg)

    return {"message": "Volunteer successfully approved for mission team."}

@router.post("/{campaign_id}/complete")
async def complete_ngo_campaign(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> dict:
    """
    Step 5 & 6: Completion & Reporting.
    Mission ends ➡️ Inventory deducted ➡️ Impact report generated.
    """
    stmt = select(NGO_Campaign).where(
        NGO_Campaign.id == campaign_id, 
        NGO_Campaign.org_id == current_user.org_id
    )
    campaign = (await db.execute(stmt)).scalar_one_or_none()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    if campaign.status == CampaignStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Action already marked as complete.")
        
    # 1. Finalize Internal Stock Deduction
    inventory_summary = []
    if campaign.items:
        for item_name, qty in campaign.items.items():
            stmt_inv = select(Inventory).where(
                Inventory.org_id == current_user.org_id,
                Inventory.item_name == item_name
            )
            inv_item = (await db.execute(stmt_inv)).scalar_one()
            inv_item.reserved_quantity -= qty
            inv_item.quantity -= qty
            inventory_summary.append(f"{qty} {inv_item.unit} of {item_name}")

    # 2. Get Performance Summary
    approved_volunteers = (await db.execute(select(Volunteer).join(MissionTeam).where(
        MissionTeam.campaign_id == campaign_id,
        MissionTeam.status == CampaignParticipationStatus.APPROVED
    ))).scalars().all()
    
    for vol in approved_volunteers:
        stats_stmt = select(VolunteerStats).where(VolunteerStats.volunteer_id == vol.id)
        stats = (await db.execute(stats_stmt)).scalar_one()
        stats.completions += 1

    campaign.status = CampaignStatus.COMPLETED
    await db.commit()

    return {
        "status": "MISSION_ACCOMPLISHED",
        "impact_summary": {
            "campaign_name": campaign.name,
            "team_size": len(approved_volunteers),
            "resources_deployed": inventory_summary,
            "completion_time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        }
    }

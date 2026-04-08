from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from sqlalchemy.orm import selectinload
from backend.app.database import get_db, async_session
from backend.app.config import settings
from backend.app.models import (
    NGO_Campaign as Campaign, CampaignStatus, Organization, Inventory, 
    Volunteer, MissionTeam as CampaignParticipation, CampaignParticipationStatus, User,
    AuditTrail
)
from backend.app.api.deps import get_current_user
from backend.app.services.telegram_service import telegram_service
from backend.app.agents.campaign_agent import campaign_agent
from typing import List, Optional, Any
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

class DraftRequest(BaseModel):
    prompt: str

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

# --- Background Tasks ---

async def background_mission_broadcast(campaign_id: int, org_id: int, org_name: str):
    """
    Asynchronous background task to broadcast mission invitations to volunteers.
    Ensures the main API request returns immediately while Telegram messages
    are sent sequentially in the background.
    """
    print(f"[TRACE] Starting Background Broadcast for Mission: {campaign_id}")
    async with async_session() as db:
        try:
            # 1. Fetch the mission details
            stmt_c = select(Campaign).where(Campaign.id == campaign_id)
            campaign = (await db.execute(stmt_c)).scalar_one_or_none()
            if not campaign:
                print(f"[ERROR] Mission {campaign_id} not found for broadcast.")
                return

            # 2. Fetch all active volunteers for this NGO
            vol_stmt = select(Volunteer.id, Volunteer.telegram_chat_id).where(
                Volunteer.org_id == org_id,
                Volunteer.telegram_active == True
            )
            volunteer_targets = (await db.execute(vol_stmt)).all()
            
            if not volunteer_targets:
                print(f"[TRACE] No volunteers found to notify for Mission {campaign_id}")
                return

            # 3. Construct Message (Web Link Integration)
            base_url = f"{settings.FRONTEND_URL}/missions"
            
            # --- Escaping dynamic fields for Telegram Markdown Safety ---
            esc_name = telegram_service.escape_markdown(campaign.name)
            esc_org = telegram_service.escape_markdown(org_name)
            esc_loc = telegram_service.escape_markdown(campaign.location_address or "Check instructions in link")
            esc_skills = telegram_service.escape_markdown(", ".join(campaign.required_skills) if campaign.required_skills else "Mission Supporter")
            timeline = campaign.start_time.strftime('%b %d, %H:%M') if campaign.start_time else 'TBD'
            
            success_count = 0
            for vol_id, chat_id in volunteer_targets:
                msg = (
                    f"🌟 *MISSION INVITATION* 🌟\n\n"
                    f"Greeting Hero! {esc_org} has just launched a new mission and we would love your support. "
                    f"Your contribution makes a real difference! 🙏\n\n"
                    f"📋 *Mission Brief:* {esc_name}\n"
                    f"⏳ *Timeline:* {timeline}\n"
                    f"🛠 *Role/Skills:* {esc_skills}\n"
                    f"📍 *Location:* {esc_loc}\n\n"
                    f"✨ *Are you ready to join us?*\n"
                    f"Review the full briefing and confirm your participation here:\n"
                    f"👉 [Review & Accept Mission]({base_url}/{campaign.id}?vol_id={vol_id})\n\n"
                    f"Together, let's serve! 🌏✨"
                )
                res = await telegram_service.send_message(chat_id, msg)
                if res: success_count += 1
            
            print(f"[TRACE] Broadcast Complete for Mission {campaign_id}. Success: {success_count}/{len(volunteer_targets)}")
        except Exception as e:
            print(f"[ERROR] Background Broadcast Failed: {e}")

# --- Endpoints ---

@router.post("/draft", response_model=Any)
async def generate_campaign_draft(
    request_in: DraftRequest,
    current_user: User = Depends(get_current_user)
):
    """
    AI Campaign Architect Agent:
    Takes a natural language prompt and returns a structured JSON draft 
    to populate the 'Create Campaign' form on the dashboard.
    """
    draft = await campaign_agent.generate_draft(request_in.prompt)
    return draft

@router.post("/", response_model=CampaignResponse)
async def create_campaign(
    campaign_in: CampaignCreate,
    background_tasks: BackgroundTasks,
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
    
    # 2. Log Audit Event
    audit = AuditTrail(
        org_id=current_user.org_id,
        actor_id=current_user.id,
        event_type="MISSION_LAUNCHED",
        target_id=str(new_campaign.id),
        notes=f"Mission '{new_campaign.name}' launched with items: {new_campaign.items}"
    )
    db.add(audit)

    await db.commit()
    await db.refresh(new_campaign)

    # 2. Trigger Background Broadcast
    org_name = current_user.organization.name if current_user.organization else "SahyogSync"
    background_tasks.add_task(background_mission_broadcast, new_campaign.id, current_user.org_id, org_name)
    
    return new_campaign

@router.post("/{campaign_id}/opt-in")
async def volunteer_opt_in(
    campaign_id: int,
    vol_id: int, # From URL parameter in the new web flow
    db: AsyncSession = Depends(get_db)
):
    """
    Volunteer joins the pool for a mission via the Web Interface.
    Status remains PENDING for final NGO approval.
    """
    # 1. Check if already joined
    stmt = select(CampaignParticipation).where(
        CampaignParticipation.campaign_id == campaign_id,
        CampaignParticipation.volunteer_id == vol_id
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        return {"status": "already_joined", "current_status": existing.status}
    
    # 2. Add to pool
    participation = CampaignParticipation(
        campaign_id=campaign_id,
        volunteer_id=vol_id,
        status=CampaignParticipationStatus.PENDING
    )
    db.add(participation)
    
    # 3. Notify Volunteer via Telegram
    vol_stmt = select(Volunteer).where(Volunteer.id == vol_id)
    volunteer = (await db.execute(vol_stmt)).scalar_one_or_none()
    
    campaign_stmt = (
        select(Campaign)
        .options(selectinload(Campaign.organization))
        .where(Campaign.id == campaign_id)
    )
    campaign = (await db.execute(campaign_stmt)).scalar_one_or_none()

    if volunteer and volunteer.telegram_chat_id and campaign:
        org_name = campaign.organization.name if campaign.organization else "SahyogSync"
        msg = (
            f"🙌 *Thank you for your readiness!*\n\n"
            f"We have received your interest for the mission: *{campaign.name}*.\n\n"
            f"We will notify you once you are *approved* by {org_name}. Stay tuned! 🚀"
        )
        await telegram_service.send_message(volunteer.telegram_chat_id, msg)

    await db.commit()
    return {"status": "success", "message": "You have expressed interest! Awaiting NGO confirmation."}

@router.post("/{campaign_id}/reject")
async def volunteer_reject(
    campaign_id: int,
    vol_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Volunteer declines the mission via the Web Interface.
    Status set to REJECTED.
    """
    stmt = select(CampaignParticipation).where(
        CampaignParticipation.campaign_id == campaign_id,
        CampaignParticipation.volunteer_id == vol_id
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    
    if existing:
        existing.status = CampaignParticipationStatus.REJECTED
    else:
        # Create a record if it doesn't exist (initial rejection)
        participation = CampaignParticipation(
            campaign_id=campaign_id,
            volunteer_id=vol_id,
            status=CampaignParticipationStatus.REJECTED
        )
        db.add(participation)
        
    await db.commit()
    return {"status": "success", "message": "Mission declined."}

@router.get("/{campaign_id}/pool", response_model=List[ParticipantResponse])
async def list_potential_volunteers(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List ALL volunteers for this campaign.
    Keeps approved/rejected visible instead of disappearing.
    """

    stmt = (
        select(CampaignParticipation, Volunteer.name, Volunteer.skills)
        .join(Volunteer, CampaignParticipation.volunteer_id == Volunteer.id)
        .where(
            CampaignParticipation.campaign_id == campaign_id
        )
    )

    result = await db.execute(stmt)

    participants = []
    for row in result:
        part, name, skills = row
        participants.append(
            ParticipantResponse(
                volunteer_id=part.volunteer_id,
                volunteer_name=name,
                skills=skills,
                status=part.status,
                joined_at=part.joined_at
            )
        )

    # sort: pending → approved → rejected
    priority = {
        CampaignParticipationStatus.PENDING: 0,
        CampaignParticipationStatus.APPROVED: 1,
        CampaignParticipationStatus.REJECTED: 2,
    }

    participants.sort(
        key=lambda p: (priority.get(p.status, 99), p.joined_at)
    )

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
    
    if campaign.volunteers_required > 0 and approved_count >= campaign.volunteers_required:
        raise HTTPException(status_code=400, detail="Campaign volunteer quota already reached!")

    # 2. Update Status
    stmt = select(CampaignParticipation).where(
        CampaignParticipation.campaign_id == campaign_id,
        CampaignParticipation.volunteer_id == vol_id
    )
    participation = (await db.execute(stmt)).scalar_one_or_none()
    if not participation:
        raise HTTPException(status_code=404, detail="Participation record not found")
    
    if participation.status == CampaignParticipationStatus.APPROVED:
        return {"status": "already_approved"}

    if participation.status == CampaignParticipationStatus.REJECTED:
        raise HTTPException(status_code=400, detail="Cannot approve a rejected volunteer")
    
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

    # 3. Log Audit Event
    audit = AuditTrail(
        org_id=campaign.org_id,
        actor_id=current_user.id,
        event_type="MISSION_COMPLETED",
        target_id=str(campaign.id),
        notes=f"Mission '{campaign.name}' completed. Volunteers: {len(approved_volunteers)}, Items: {campaign.items}"
    )
    db.add(audit)
                
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

@router.post("/{campaign_id}/broadcast")
async def trigger_manual_broadcast(
    campaign_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Manually re-trigger the broadcast for a specific campaign.
    Useful for notifying newly verified volunteers or retrying failures.
    """
    stmt = select(Campaign).where(Campaign.id == campaign_id, Campaign.org_id == current_user.org_id)
    campaign = (await db.execute(stmt)).scalar_one_or_none()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    org_name = current_user.organization.name if current_user.organization else "SahyogSync"
    background_tasks.add_task(background_mission_broadcast, campaign.id, current_user.org_id, org_name)
    
    return {"status": "success", "message": f"Broadcast triggered for {campaign.name}"}

@router.get("/", response_model=List[CampaignResponse])
async def list_campaigns(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(Campaign).where(Campaign.org_id == current_user.org_id)
    result = await db.execute(stmt)
    return result.scalars().all()

@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: int,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Campaign).where(Campaign.id == campaign_id)
    campaign = (await db.execute(stmt)).scalar_one_or_none()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    return campaign

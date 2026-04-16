from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from backend.app.database import get_db
from backend.app.models import (
    MarketplaceDispatch, 
    MarketplaceNeed, 
    Volunteer, 
    DispatchStatus, 
    NeedStatus, 
    User, 
    VolunteerStats,
    MarketplaceInventory,
    VolunteerStatus
)
from backend.app.api.deps import get_current_user
from backend.app.services.otp import verify_otp
from backend.app.services.telegram_service import telegram_service
from backend.app.notifications.service import notification_service
from backend.app.volunteers.service import increment_volunteer_completions
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import List, Optional

# --- Schemas ---

class MarketplaceDispatchCreate(BaseModel):
    marketplace_need_id: int
    volunteer_ids: List[int]

class VerifyOTPRequest(BaseModel):
    dispatch_id: int
    otp_code: str = Field(..., max_length=6, min_length=6)

class MarketplaceDispatchResponse(BaseModel):
    id: int
    marketplace_need_id: int
    volunteer_id: int
    status: DispatchStatus
    created_at: datetime
    otp_used: bool

    # --- Enhanced Fields ---
    volunteer_name: Optional[str] = None
    item_type: Optional[str] = None
    item_quantity: Optional[str] = None
    pickup_address: Optional[str] = None

    class Config:
        from_attributes = True

# --- Router ---

router = APIRouter()

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_marketplace_dispatch(
    data: MarketplaceDispatchCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Coordinator selects one or more volunteers for a Marketplace Need.
    Enables FCFS (First-Come, First-Served) logic.
    """
    # 1. Verify MarketplaceNeed exists and belongs to NGO
    need_stmt = select(MarketplaceNeed).where(
        MarketplaceNeed.id == data.marketplace_need_id, 
        MarketplaceNeed.org_id == current_user.org_id
    )
    need = (await db.execute(need_stmt)).scalar_one_or_none()
    if not need:
        raise HTTPException(status_code=404, detail="Marketplace need not found in your organization")

    # 2. Verify Volunteers exist and belong to NGO
    vol_stmt = select(Volunteer).where(
        Volunteer.id.in_(data.volunteer_ids),
        Volunteer.org_id == current_user.org_id
    )
    volunteers = (await db.execute(vol_stmt)).scalars().all()
    
    if len(volunteers) != len(data.volunteer_ids):
        raise HTTPException(status_code=404, detail="One or more volunteers not found in your organization")
    
    # Check availability
    for v in volunteers:
        if v.status != VolunteerStatus.AVAILABLE:
            raise HTTPException(status_code=400, detail=f"Volunteer {v.name} is not available for dispatch (Status: {v.status.value})")
    
    # 3. Create Dispatches and Notify
    created_dispatches = []
    for volunteer in volunteers:
        if not volunteer.telegram_active or not volunteer.telegram_chat_id:
            continue # Skip inactive volunteers for now, or could raise error
            
        dispatch = MarketplaceDispatch(
            marketplace_need_id=data.marketplace_need_id,
            volunteer_id=volunteer.id,
            status=DispatchStatus.SENT
        )
        db.add(dispatch)
        created_dispatches.append(dispatch)
    
    if not created_dispatches:
        raise HTTPException(status_code=400, detail="No active volunteers selected for dispatch.")

    # Mark need as DISPATCHED (waiting for someone to accept)
    need.status = NeedStatus.DISPATCHED
    
    await db.commit()
    
    # 4. Fire Telegram Notifications
    # --- Escaping dynamic fields for Telegram Markdown Safety ---
    esc_type = telegram_service.escape_markdown(need.type.name)
    esc_qty = telegram_service.escape_markdown(need.quantity)
    esc_addr = telegram_service.escape_markdown(need.pickup_address)

    # Optional Map Link
    nav_link = ""
    if need.latitude and need.longitude:
        nav_link = f"🗺️ *Map*: [View Pickup Spot](https://www.google.com/maps/search/?api=1&query={need.latitude},{need.longitude})\n"

    body = (
        f"🚨 *New Donation Pickup ALERT*\n\n"
        f"Hero, you have been invited to collect a donor's contribution:\n"
        f"📦 *Type*: {esc_type}\n"
        f"🔢 *Qty*: {esc_qty}\n"
        f"📍 *Pickup*: {esc_addr}\n"
        f"{nav_link}\n"
        "⚡ *ACT FAST*: This mission is available on a first-come, first-served basis. Tap accept now to claim it! 🤝"
    )
    
    success_count = 0
    for dispatch in created_dispatches:
        keyboard = {
            "inline_keyboard": [[
                {"text": "✅ Accept Mission", "callback_data": f"accept_{dispatch.id}"},
                {"text": "❌ Decline", "callback_data": f"decline_{dispatch.id}"}
            ]]
        }
        # Find the volunteer's chat ID from the already-fetched list
        vol_chat_id = next((v.telegram_chat_id for v in volunteers if v.id == dispatch.volunteer_id), None)
        
        if vol_chat_id:
            res = await telegram_service.send_message(
                chat_id=vol_chat_id,
                text=body,
                reply_markup=keyboard
            )
            if res: success_count += 1
    
    print(f"[TRACE] Marketplace Dispatch Loop Complete. Success: {success_count}/{len(created_dispatches)}")

    return {"message": f"Marketplace dispatch sent to {len(created_dispatches)} volunteers", "dispatch_ids": [d.id for d in created_dispatches]}

@router.post("/verify-otp", response_model=dict)
async def verify_marketplace_otp(
    data: VerifyOTPRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Verify the 6-digit OTP code provided to the Donor.
    SUCCESS: Auto-populates 'MarketplaceInventory' (The Recovery Layer).
    """
    stmt = (
        select(MarketplaceDispatch)
        .join(Volunteer, MarketplaceDispatch.volunteer_id == Volunteer.id)
        .where(MarketplaceDispatch.id == data.dispatch_id, Volunteer.org_id == current_user.org_id)
    )
    dispatch = (await db.execute(stmt)).scalar_one_or_none()
    
    if not dispatch:
        raise HTTPException(status_code=404, detail="Dispatch record not found")

    if dispatch.otp_used:
        raise HTTPException(status_code=400, detail="OTP already used")
    
    # 1. Status Check: Only ACCEPTED missions have valid OTPs
    if dispatch.status != DispatchStatus.ACCEPTED:
        raise HTTPException(status_code=400, detail="Mission is not in ACCEPTED state. Verification not possible.")

    # 2. Expiry Check
    if dispatch.otp_expires_at and datetime.utcnow() > dispatch.otp_expires_at:
        raise HTTPException(status_code=401, detail="OTP has expired. Please re-generate or re-accept the mission.")

    # 3. Verify Code
    if not dispatch.otp_hash or not verify_otp(data.otp_code, dispatch.otp_hash):
        dispatch.otp_attempts += 1
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid OTP code.")

    # --- Success Logic ---
    dispatch.otp_used = True
    dispatch.status = DispatchStatus.COMPLETED 
    
    # Update MarketplaceNeed
    stmt_need = select(MarketplaceNeed).where(MarketplaceNeed.id == dispatch.marketplace_need_id)
    need = (await db.execute(stmt_need)).scalar_one()
    need.status = NeedStatus.COMPLETED

    # 1. AUTO-POPULATE MarketplaceInventory (The 'Recovery' History)
    recovery_entry = MarketplaceInventory(
        org_id=current_user.org_id,
        item_name=f"Recovered {need.type.name}", # e.g. Recovered FOOD
        quantity=1.0, # Placeholder quantity if not parsed as float
        unit=need.quantity, # Store original quantity string as unit/desc
        collected_at=datetime.now(timezone.utc)
    )
    db.add(recovery_entry)

    # 2. Update VolunteerStats
    await increment_volunteer_completions(db, dispatch.volunteer_id)

    # 3. Reset Volunteer Status to AVAILABLE
    stmt_vol = select(Volunteer).where(Volunteer.id == dispatch.volunteer_id)
    volunteer = (await db.execute(stmt_vol)).scalar_one()
    volunteer.status = VolunteerStatus.AVAILABLE

    await db.commit()

    # --- Notification Center: Mission Completed (Manual OTP) ---
    await notification_service.notify_mission_completed(
        db=db,
        org_id=current_user.org_id,
        mission_name=need.type.name
    )

    return {"status": "success", "message": "OTP verified. Recovery logged in MarketplaceInventory."}

@router.get("/", response_model=List[MarketplaceDispatchResponse])
async def list_marketplace_dispatch_history(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all historical marketplace dispatches for the current NGO.
    Includes descriptive names and types for easy coordinate viewing.
    """
    from sqlalchemy.orm import joinedload
    
    stmt = (
        select(MarketplaceDispatch)
        .options(
            joinedload(MarketplaceDispatch.volunteer),
            joinedload(MarketplaceDispatch.marketplace_need)
        )
        .join(MarketplaceNeed, MarketplaceDispatch.marketplace_need_id == MarketplaceNeed.id)
        .where(MarketplaceNeed.org_id == current_user.org_id)
        .order_by(MarketplaceDispatch.created_at.desc())
    )
    
    result = await db.execute(stmt)
    dispatches = result.scalars().all()
    
    # Map to Response model manually to flatten the joined data
    response_list = []
    for d in dispatches:
        resp = MarketplaceDispatchResponse.model_validate(d)
        resp.volunteer_name = d.volunteer.name if d.volunteer else "Unknown"
        resp.item_type = d.marketplace_need.type.name if d.marketplace_need else "Unknown"
        resp.item_quantity = d.marketplace_need.quantity if d.marketplace_need else "N/A"
        resp.pickup_address = d.marketplace_need.pickup_address if d.marketplace_need else "N/A"
        response_list.append(resp)
        
    return response_list

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
    MarketplaceInventory
)
from backend.app.api.deps import get_current_user
from backend.app.services.otp import verify_otp
from backend.app.services.telegram_service import telegram_service
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional

# --- Schemas ---

class MarketplaceDispatchCreate(BaseModel):
    marketplace_need_id: int
    volunteer_id: int

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
    Coordinator manually selects a volunteer for a Marketplace Need.
    Speed Layer: 1-to-1 reactive mission.
    """
    # 1. Verify MarketplaceNeed exists and belongs to NGO
    need_stmt = select(MarketplaceNeed).where(
        MarketplaceNeed.id == data.marketplace_need_id, 
        MarketplaceNeed.org_id == current_user.org_id
    )
    need = (await db.execute(need_stmt)).scalar_one_or_none()
    if not need:
        raise HTTPException(status_code=404, detail="Marketplace need not found in your organization")

    # 2. Verify Volunteer exists and belongs to NGO
    vol_stmt = select(Volunteer).where(
        Volunteer.id == data.volunteer_id,
        Volunteer.org_id == current_user.org_id
    )
    volunteer = (await db.execute(vol_stmt)).scalar_one_or_none()
    if not volunteer:
        raise HTTPException(status_code=404, detail="Volunteer not found in your organization")
    
    if not volunteer.telegram_active or not volunteer.telegram_chat_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Volunteer must activate Telegram bot first."
        )

    # 3. Create MarketplaceDispatch
    dispatch = MarketplaceDispatch(
        marketplace_need_id=data.marketplace_need_id,
        volunteer_id=data.volunteer_id,
        status=DispatchStatus.SENT
    )
    db.add(dispatch)
    need.status = NeedStatus.DISPATCHED

    await db.commit()
    await db.refresh(dispatch)

    # 4. Fire Telegram Notification
    body = (
        f"🚨 *Marketplace Mission ALERT*\n\n"
        f"You have been assigned to collect a donor surplus:\n"
        f"*Type*: {need.type.name}\n"
        f"*Qty*: {need.quantity}\n"
        f"*Pickup*: {need.pickup_address}\n\n"
        "Please go to the location and collect the items."
    )
    
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Accept Mission", "callback_data": f"accept_{dispatch.id}"},
            {"text": "❌ Decline", "callback_data": f"decline_{dispatch.id}"}
        ]]
    }
    
    await telegram_service.send_message(
        chat_id=volunteer.telegram_chat_id,
        text=body,
        reply_markup=keyboard
    )

    return {"message": "Marketplace dispatch created", "dispatch_id": dispatch.id}

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

    # Verify logic
    if not verify_otp(data.otp_code, dispatch.otp_hash):
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
        collected_at=datetime.utcnow()
    )
    db.add(recovery_entry)

    # 2. Update VolunteerStats
    stats_stmt = select(VolunteerStats).where(VolunteerStats.volunteer_id == dispatch.volunteer_id)
    stats = (await db.execute(stats_stmt)).scalar_one()
    stats.completions += 1

    await db.commit()

    return {"status": "success", "message": "OTP verified. Recovery logged in MarketplaceInventory."}

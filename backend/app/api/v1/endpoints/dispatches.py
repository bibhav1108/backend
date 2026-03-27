from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from backend.app.database import get_db
from backend.app.models import Dispatch, Need, Volunteer, DispatchStatus, NeedStatus, User, VolunteerStats
from backend.app.api.deps import get_current_user
from backend.app.services.otp import verify_otp
from backend.app.services.telegram_service import telegram_service
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional

class DispatchCreate(BaseModel):
    need_id: int
    volunteer_id: int

class VerifyOTPRequest(BaseModel):
    dispatch_id: int
    otp_code: str = Field(..., max_length=6, min_length=6)

class DispatchResponse(BaseModel):
    id: int
    need_id: int
    volunteer_id: int
    status: DispatchStatus
    created_at: datetime
    otp_used: bool

    class Config:
        from_attributes = True

router = APIRouter()

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_dispatch(
    data: DispatchCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Coordinator manually selects a volunteer and triggers dispatch broadcast.
    Saves Dispatch status as 'SENT' and alerts Volunteer over Telegram.
    """
    # 1. Verify Need exists and belongs to NGO
    need_stmt = select(Need).where(
        Need.id == data.need_id, 
        Need.org_id == current_user.org_id
    )
    need = (await db.execute(need_stmt)).scalar_one_or_none()
    if not need:
        raise HTTPException(status_code=404, detail="Need not found in your organization")

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
            detail="Volunteer must activate Telegram bot activation gate first."
        )

    # 3. Create Dispatch
    dispatch = Dispatch(
        need_id=data.need_id,
        volunteer_id=data.volunteer_id,
        status=DispatchStatus.SENT
    )
    db.add(dispatch)
    need.status = NeedStatus.DISPATCHED  # Update status lifecycle

    # Update VolunteerStats (last_dispatch_at)
    async with db.begin_nested():
        stmt_stats = select(VolunteerStats).where(VolunteerStats.volunteer_id == volunteer.id)
        stats = (await db.execute(stmt_stats)).scalar_one_or_none()
        if stats:
            stats.last_dispatch_at = datetime.utcnow()

    await db.commit()
    await db.refresh(dispatch)

    # 4. Fire Telegram Notification
    body = (
        f"*Sahyog Setu - New Mission ALERT*\n\n"
        f"You have been dispatched to match a target need:\n"
        f"*Type*: {need.type.name}\n"
        f"*Qty*: {need.quantity}\n"
        f"*Pickup*: {need.pickup_address}\n\n"
        "Click the button below to accept:"
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

    return {"message": "Dispatch created and alert fired", "dispatch_id": dispatch.id}

@router.get("/", response_model=List[DispatchResponse])
async def list_dispatches(
    status: Optional[DispatchStatus] = None,
    volunteer_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List historical dispatches for the current NGO.
    Filters: status, volunteer_id.
    """
    stmt = (
        select(Dispatch)
        .join(Need, Dispatch.need_id == Need.id)
        .where(Need.org_id == current_user.org_id)
    )
    
    if status:
        stmt = stmt.where(Dispatch.status == status)
    if volunteer_id:
        stmt = stmt.where(Dispatch.volunteer_id == volunteer_id)
        
    stmt = stmt.order_by(Dispatch.created_at.desc())
    
    result = await db.execute(stmt)
    return result.scalars().all()
async def verify_dispatch_otp(
    data: VerifyOTPRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Verify the 6-digit OTP code provided to the Donor to confirm complete.
    Marks the Need as COMPLETE if successful.
    """
    # 1. Lookup Dispatch (Enforce isolation - need a join to verify org_id of volunteer or need)
    stmt = (
        select(Dispatch)
        .join(Volunteer, Dispatch.volunteer_id == Volunteer.id)
        .where(Dispatch.id == data.dispatch_id, Volunteer.org_id == current_user.org_id)
    )
    dispatch = (await db.execute(stmt)).scalar_one_or_none()
    
    if not dispatch:
        raise HTTPException(status_code=404, detail="Dispatch record not found in your organization")

    # Update dispatch status to ACCEPTED if it was SENT
    if dispatch.status == DispatchStatus.SENT:
        dispatch.status = DispatchStatus.ACCEPTED
        await db.commit() # Commit the status change immediately

    # 2. Check if already locked/failed
    if dispatch.otp_attempts >= 3:
        dispatch.status = DispatchStatus.FAILED
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="OTP locked. Maximum attempts (3) exceeded. Mission aborted."
        )

    if dispatch.otp_used:
        raise HTTPException(status_code=400, detail="OTP already used")

    # 3. Check expiration
    if dispatch.otp_expires_at and datetime.utcnow() > dispatch.otp_expires_at:
         raise HTTPException(status_code=400, detail="OTP expired (45 min limit)")

    # 4. Verify logic with attempt increment
    if not dispatch.otp_hash:
        raise HTTPException(status_code=400, detail="OTP has not been generated for this dispatch yet.")

    if not verify_otp(data.otp_code, dispatch.otp_hash):
        dispatch.otp_attempts += 1
        
        remaining = 3 - dispatch.otp_attempts
        detail = f"Invalid OTP code. {remaining} attempts remaining."
        if remaining <= 0:
            dispatch.status = DispatchStatus.FAILED
            # INCR No-shows
            stats_stmt = select(VolunteerStats).where(VolunteerStats.volunteer_id == dispatch.volunteer_id)
            stats = (await db.execute(stats_stmt)).scalar_one()
            stats.no_shows += 1
            detail = "Invalid OTP code. Maximum attempts exceeded. Mission aborted."
            
        await db.commit()
        raise HTTPException(status_code=401, detail=detail)

    # Success Logic
    dispatch.otp_used = True
    dispatch.status = DispatchStatus.COMPLETED 
    
    # Update Need lifecycle
    stmt_need = select(Need).where(Need.id == dispatch.need_id)
    need = (await db.execute(stmt_need)).scalar_one()
    need.status = NeedStatus.COMPLETED

    # Update VolunteerStats (completions++)
    stats_stmt = select(VolunteerStats).where(VolunteerStats.volunteer_id == dispatch.volunteer_id)
    stats = (await db.execute(stats_stmt)).scalar_one()
    stats.completions += 1

    await db.commit()

    return {"status": "success", "message": "OTP verified successfully. Record complete."}

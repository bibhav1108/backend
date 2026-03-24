from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.database import get_db
from backend.app.models import Dispatch, Need, Volunteer, DispatchStatus, NeedStatus
from backend.app.services.otp import verify_otp
from backend.app.services.twilio_service import twilio_service
from pydantic import BaseModel, Field
from datetime import datetime

class DispatchCreate(BaseModel):
    need_id: int
    volunteer_id: int

class VerifyOTPRequest(BaseModel):
    dispatch_id: int
    otp_code: str = Field(..., max_length=6, min_length=6)

router = APIRouter()

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_dispatch(
    data: DispatchCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Coordinator manually selects a volunteer and triggers dispatch broadcast.
    Saves Dispatch status as 'SENT' and alerts Volunteer over WhatsApp.
    """
    # 1. Verify Need exists
    need_stmt = select(Need).where(Need.id == data.need_id)
    need = (await db.execute(need_stmt)).scalar_one_or_none()
    if not need:
        raise HTTPException(status_code=404, detail="Need not found")

    # 2. Verify Volunteer exists and is WhatsApp active
    vol_stmt = select(Volunteer).where(Volunteer.id == data.volunteer_id)
    volunteer = (await db.execute(vol_stmt)).scalar_one_or_none()
    if not volunteer:
        raise HTTPException(status_code=404, detail="Volunteer not found")
    
    if not volunteer.whatsapp_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Volunteer must activate WhatsApp activation gate first."
        )

    # 3. Create Dispatch
    dispatch = Dispatch(
        need_id=data.need_id,
        volunteer_id=data.volunteer_id,
        status=DispatchStatus.SENT
    )
    db.add(dispatch)
    need.status = NeedStatus.DISPATCHED  # Update status lifecycle

    await db.commit()
    await db.refresh(dispatch)

    # 4. Fire Twilio Notify
    # Format message for WhatsApp
    body = (
        f"*Sahyog Setu - New Mission ALERT*\n\n"
        f"You have been dispatched to match a target need:\n"
        f"*Type*: {need.type.name}\n"
        f"*Qty*: {need.quantity}\n"
        f"*Pickup*: {need.pickup_address}\n\n"
        f"Reply with **`YES`** within 5 minutes to confirm assignment."
    )
    
    await twilio_service.send_whatsapp_message(
        to_number=f"whatsapp:{volunteer.phone_number}",
        body=body
    )

    return {"message": "Dispatch created and alert fired", "dispatch_id": dispatch.id}



@router.post("/verify-otp")
async def verify_dispatch_otp(
    data: VerifyOTPRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Verify the 6-digit OTP code provided to the Donor to confirm complete.
    Marks the Need as COMPLETE if successful.
    """
    stmt = select(Dispatch).where(Dispatch.id == data.dispatch_id)
    dispatch = (await db.execute(stmt)).scalar_one_or_none()
    
    if not dispatch:
        raise HTTPException(status_code=404, detail="Dispatch record not found")

    if dispatch.otp_used:
        raise HTTPException(status_code=400, detail="OTP already used")

    # Check expiration
    if dispatch.otp_expires_at and datetime.utcnow() > dispatch.otp_expires_at:
         raise HTTPException(status_code=400, detail="OTP expired (45 min limit)")

    # Verify logic
    if not verify_otp(data.otp_code, dispatch.otp_hash):
        raise HTTPException(status_code=401, detail="Invalid OTP code")

    # Success
    dispatch.otp_used = True
    dispatch.status = DispatchStatus.CONFIRMED # ensure confirmed, maybe complete on need
    
    # Update Need lifecycle
    stmt_need = select(Need).where(Need.id == dispatch.need_id)
    need = (await db.execute(stmt_need)).scalar_one()
    need.status = NeedStatus.COMPLETED

    await db.commit()

    return {"status": "success", "message": "OTP verified successfully. Record complete."}

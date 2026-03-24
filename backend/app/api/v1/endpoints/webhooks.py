from fastapi import APIRouter, Depends, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.database import get_db
from backend.app.models import Volunteer, Dispatch, DispatchStatus
from backend.app.services.otp import generate_otp_pair
from backend.app.services.twilio_service import twilio_service

router = APIRouter()

@router.post("/whatsapp")
async def whatsapp_webhook(
    From: str = Form(...),
    Body: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Handle incoming WhatsApp responses.
    Expects Twilio Form variables: From and Body
    """
    # Twilio sends From as "whatsapp:+1234567890"
    clean_phone = From.replace("whatsapp:", "").strip()
    reply_text = Body.strip().upper()

    # 1. Lookup Volunteer
    stmt = select(Volunteer).where(Volunteer.phone_number == clean_phone)
    result = await db.execute(stmt)
    volunteer = result.scalar_one_or_none()

    if not volunteer:
        print(f"[Webhook LOG] Message from unregistered number: {clean_phone}")
        return {"status": "unregistered"}

    # --- [NEW] WhatsApp Activation Gate ---
    if not volunteer.whatsapp_active:
        if reply_text in ["ACTIVATE", "YES"]:
            volunteer.whatsapp_active = True
            await db.commit()
            await twilio_service.send_whatsapp_message(
                to_number=From,
                body=(
                    f"*Sahyog Setu - Account Activated!*\n\n"
                    f"Welcome, *{volunteer.name}*!\n"
                    f"You are now ready to receive automated dispatch alerts for needs and coordination."
                )
            )
            return {"status": "activated"}
        return {"status": "inactive_needs_activation", "msg": "Send ACTIVATE to turn on accounts"}

    # 2. Lookup active/sent Dispatch

    stmt = (
        select(Dispatch)
        .where(
            Dispatch.volunteer_id == volunteer.id,
            Dispatch.status == DispatchStatus.SENT
        )
        .order_by(Dispatch.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    dispatch = result.scalar_one_or_none()

    if not dispatch:
        print(f"[Webhook LOG] No active dispatch found for: {volunteer.name}")
        return {"status": "no_active_dispatch"}

    if reply_text == "YES":
        # 3. Lock as Confirmed / Accepted
        # (Roadmap uses SENT -> CONFIRMED for assignment lock step)
        dispatch.status = DispatchStatus.CONFIRMED
        
        # 4. Generate & Save OTP
        raw_code, hashed, expires_at = generate_otp_pair()
        dispatch.otp_hash = hashed
        dispatch.otp_expires_at = expires_at
        dispatch.otp_used = False

        await db.commit()

        # 5. Send Code back to Volunteer
        await twilio_service.send_whatsapp_message(
            to_number=From,
            body=(
                f"*Sahyog Setu - Dispatch Confirmed*\n\n"
                f"Your pickup unique code is: *{raw_code}*\n"
                f"This code is valid for 45 minutes.\n"
                f"Please provide this to the donor upon arrival."
            )
        )
        return {"status": "confirmed", "otp_sent": True}
        

    print(f"[Webhook LOG] Unrecognized reply from {volunteer.name}: {Body}")
    return {"status": "reply_not_recognized"}

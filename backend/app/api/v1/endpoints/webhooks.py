from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.database import get_db
from backend.app.models import Volunteer, Dispatch, DispatchStatus, SurplusAlert
from backend.app.services.otp import generate_otp_pair
from backend.app.services.telegram_service import telegram_service

router = APIRouter()

@router.post("/telegram")
async def telegram_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle incoming Telegram Bot updates.
    """
    data = await request.json()
    
    if "message" not in data:
        return {"status": "ignored"}

    message = data["message"]
    chat_id = str(message["chat"]["id"])
    text = message.get("text", "").strip().upper()

    # 1. Lookup Volunteer by telegram_chat_id or attempt registration link
    stmt = select(Volunteer).where(Volunteer.telegram_chat_id == chat_id)
    result = await db.execute(stmt)
    volunteer = result.scalar_one_or_none()

    if not volunteer:
        # Fallback: check if the user is sending "ACTIVATE <PHONE>" or similar
        # For MVP, we'll assume the user needs to be linked.
        if text.startswith("ACTIVATE"):
            parts = text.split()
            if len(parts) > 1:
                phone = parts[1].replace("+", "").strip()
                # Lookup by phone
                stmt = select(Volunteer).where(Volunteer.phone_number == phone)
                result = await db.execute(stmt)
                volunteer = result.scalar_one_or_none()
                
                if volunteer:
                    volunteer.telegram_chat_id = chat_id
                    volunteer.telegram_active = True
                    await db.commit()
                    await telegram_service.send_message(
                        chat_id=chat_id,
                        text=(
                            f"✅ *Sahyog Setu - Account Activated!*\n\n"
                            f"Welcome, *{volunteer.name}*!\n"
                            f"Your Telegram account is now linked to your volunteer profile. "
                            f"You will receive dispatch alerts here."
                        )
                    )
                    return {"status": "activated"}
            
            
        # 🟢 [REPLACEMENT] Donor Flow catch-all
        alert = SurplusAlert(
            chat_id=chat_id,
            message_body=text,
            donor_name=message.get("from", {}).get("first_name", "Anonymous Donor")
        )
        db.add(alert)
        await db.commit()

        await telegram_service.send_message(
            chat_id=chat_id,
            text=(
                "🙏 *Sahyog Setu - Thank you!*\n\n"
                "Your surplus report has been received and shared with local NGOs. "
                "Someone will contact you soon if a match is found."
            )
        )
        return {"status": "surplus_alert_saved"}

    # 2. If already linked but not active
    if not volunteer.telegram_active:
        if text in ["ACTIVATE", "YES"]:
            volunteer.telegram_active = True
            await db.commit()
            await telegram_service.send_message(
                chat_id=chat_id,
                text=f"✅ *Sahyog Setu - Activated!*\n\nWelcome back, *{volunteer.name}*."
            )
            return {"status": "activated"}
        return {"status": "inactive"}

    # 3. Lookup active/sent Dispatch
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
        return {"status": "no_active_dispatch"}

    if text == "YES":
        dispatch.status = DispatchStatus.CONFIRMED
        raw_code, hashed, expires_at = generate_otp_pair()
        dispatch.otp_hash = hashed
        dispatch.otp_expires_at = expires_at
        dispatch.otp_used = False

        await db.commit()

        await telegram_service.send_message(
            chat_id=chat_id,
            text=(
                f"🎫 *Sahyog Setu - Dispatch Confirmed*\n\n"
                f"Your pickup unique code is: `{raw_code}`\n"
                f"Valid for 45 minutes.\n"
                f"Show this to the donor."
            )
        )
        return {"status": "confirmed"}

    return {"status": "ignored"}

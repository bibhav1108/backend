from fastapi import APIRouter, Depends, Request
import traceback
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from backend.app.database import get_db
from backend.app.models import Volunteer, Dispatch, DispatchStatus, SurplusAlert, Organization
from backend.app.services.otp import generate_otp_pair
from backend.app.services.telegram_service import telegram_service

router = APIRouter()

@router.post("/telegram")
async def telegram_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle incoming Telegram Bot updates (Messages, Contacts, Callbacks).
    """
    try:
        data = await request.json()
        print(f"[DEBUG] Webhook Data: {data}")
        
        # --- 1. Handle Button Callbacks (Inline Buttons) ---
        if "callback_query" in data:
            callback = data["callback_query"]
            chat_id = str(callback["message"]["chat"]["id"])
            data_payload = callback.get("data", "")
            
            # Identify Volunteer
            stmt = select(Volunteer).where(Volunteer.telegram_chat_id == chat_id)
            volunteer = (await db.execute(stmt)).scalar_one_or_none()
            
            if data_payload.startswith("accept_") and volunteer:
                dispatch_id = int(data_payload.split("_")[1])
                stmt = select(Dispatch).where(Dispatch.id == dispatch_id, Dispatch.volunteer_id == volunteer.id)
                dispatch = (await db.execute(stmt)).scalar_one_or_none()
                
                if dispatch and dispatch.status == DispatchStatus.SENT:
                    dispatch.status = DispatchStatus.CONFIRMED
                    raw_code, hashed, expires_at = generate_otp_pair()
                    dispatch.otp_hash = hashed
                    dispatch.otp_expires_at = expires_at
                    await db.commit()
                    
                    await telegram_service.send_message(
                        chat_id=chat_id,
                        text=f"🎫 *Mission Confirmed!*\n\nYour Pickup CODE is: `{raw_code}`\nValid for 45 mins."
                    )
            return {"status": "callback_handled"}

        if "message" not in data:
            return {"status": "ignored"}

        message = data["message"]
        chat_id = str(message["chat"]["id"])
        text = message.get("text", "").strip()
        
        # --- 2. Handle /start and Help ---
        if text == "/start":
            # Check if already active
            stmt = select(Volunteer).where(Volunteer.telegram_chat_id == chat_id)
            volunteer = (await db.execute(stmt)).scalar_one_or_none()
            
            if volunteer and volunteer.telegram_active:
                await telegram_service.send_message(
                    chat_id=chat_id,
                    text=f"Welcome back, *{volunteer.name}*! You are active and ready for missions. 🚀"
                )
            else:
                keyboard = {
                    "keyboard": [[{"text": "📱 Share Contact to Verify", "request_contact": True}]],
                    "one_time_keyboard": True,
                    "resize_keyboard": True
                }
                await telegram_service.send_message(
                    chat_id=chat_id,
                    text=(
                        "Welcome to *Sahyog Setu*! 🤝\n\n"
                        "To start receiving mission alerts, please choose a verification method:\n\n"
                        "1️⃣ *One-Click*: Click the button below to share your verified contact.\n"
                        "2️⃣ *Manual*: Type `ACTIVATE <PHONE_NUMBER>` (e.g., `ACTIVATE 9876543210`) if you prefer manual entry."
                    ),
                    reply_markup=keyboard
                )
            return {"status": "start_sent"}

        if text == "/help":
            help_text = (
                "🆘 *Sahyog Setu Help*\n\n"
                "• `/status` - Check your volunteer stats and trust tier.\n"
                "• Use the buttons in mission alerts to Accept or Decline tasks.\n"
                "• If you have surplus food to report, just type the details here!"
            )
            await telegram_service.send_message(chat_id=chat_id, text=help_text)
            return {"status": "help_sent"}

        if text == "/status":
            stmt = select(Volunteer).where(Volunteer.telegram_chat_id == chat_id)
            volunteer = (await db.execute(stmt)).scalar_one_or_none()
            
            if volunteer:
                status_report = (
                    f"👤 *Volunteer Profile*\n"
                    f"Name: {volunteer.name}\n"
                    f"Trust Tier: `{volunteer.trust_tier.name}`\n"
                    f"Completions: `{volunteer.completions}`\n"
                    f"No-Shows: `{volunteer.no_shows}`\n\n"
                    f"Status: *{'Active' if volunteer.telegram_active else 'Inactive'}*"
                )
                await telegram_service.send_message(chat_id=chat_id, text=status_report)
            else:
                await telegram_service.send_message(chat_id=chat_id, text="❌ Profile not found.")
            return {"status": "status_sent"}

        # --- 2.5 Handle Manual ACTIVATE command ---
        if text.upper().startswith("ACTIVATE"):
            parts = text.split()
            if len(parts) > 1:
                phone = parts[1].replace("+", "").strip()
                # Match with DB
                stmt = (
                    select(Volunteer)
                    .where(Volunteer.phone_number.like(f"%{phone[-10:]}%"))
                    .options(selectinload(Volunteer.organization))
                )
                volunteer = (await db.execute(stmt)).scalar_one_or_none()
                
                if volunteer:
                    volunteer.telegram_chat_id = chat_id
                    volunteer.telegram_active = True
                    await db.commit()
                    welcome_text = (
                        f"🎉 *Successfully Onboarded (Manual)!*\n\n"
                        f"👤 *Volunteer*: {volunteer.name}\n"
                        f"🏢 *Organization*: {volunteer.organization.name}\n"
                        f"📱 *Verified*: {volunteer.phone_number}\n\n"
                        f"You are now linked to *{volunteer.organization.name}*. 🚀"
                    )
                    await telegram_service.send_message(chat_id=chat_id, text=welcome_text)
                    return {"status": "linked_manual"}
                else:
                    await telegram_service.send_message(
                        chat_id=chat_id,
                        text="❌ *Error*: Number not found in our NGO database."
                    )
                    return {"status": "link_manual_failed"}

        # --- 3. Handle Contact Sharing (Verification) ---
        if "contact" in message:
            contact = message["contact"]
            phone = contact["phone_number"].replace("+", "").strip()
            
            # Match with DB
            stmt = (
                select(Volunteer)
                .where(Volunteer.phone_number.like(f"%{phone[-10:]}%")) # Match last 10 digits
                .options(selectinload(Volunteer.organization))
            )
            volunteer = (await db.execute(stmt)).scalar_one_or_none()
            
            if volunteer:
                volunteer.telegram_chat_id = chat_id
                volunteer.telegram_active = True
                await db.commit()
                
                # Rich Onboarding Message
                welcome_text = (
                    f"🎉 *Successfully Onboarded!*\n\n"
                    f"👤 *Volunteer*: {volunteer.name}\n"
                    f"🏢 *Organization*: {volunteer.organization.name}\n"
                    f"📱 *Verified*: {volunteer.phone_number}\n\n"
                    f"You are now linked to *{volunteer.organization.name}*. "
                    f"You will receive mission alerts from them directly in this chat. 🚀"
                )
                await telegram_service.send_message(
                    chat_id=chat_id,
                    text=welcome_text
                )
                return {"status": "linked"}
            else:
                await telegram_service.send_message(
                    chat_id=chat_id,
                    text="❌ *Error*: This number is not registered on the NGO dashboard. Please contact your coordinator."
                )
                return {"status": "link_failed"}

        # --- 4. Fallback: Donor Flow ---
        # Identification logic
        stmt = select(Volunteer).where(Volunteer.telegram_chat_id == chat_id)
        volunteer = (await db.execute(stmt)).scalar_one_or_none()
        
        if not volunteer:
            # Save as Surplus Alert
            alert = SurplusAlert(
                chat_id=chat_id,
                message_body=text,
                donor_name=message.get("from", {}).get("first_name", "Anonymous Donor")
            )
            db.add(alert)
            await db.commit()
            await telegram_service.send_message(
                chat_id=chat_id,
                text="🙏 *Thank you!* Your surplus report has been shared with local NGOs."
            )
            return {"status": "surplus_saved"}

    except Exception as e:
        print(f"[ERROR] Webhook Task Failed: {e}")
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

    return {"status": "ignored"}

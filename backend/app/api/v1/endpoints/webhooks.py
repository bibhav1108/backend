from fastapi import APIRouter, Depends, Request, BackgroundTasks
import traceback
from typing import Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, delete
from sqlalchemy.orm import selectinload
from backend.app.database import get_db, async_session
from backend.app.models import (
    Volunteer, 
    MarketplaceDispatch, 
    DispatchStatus, 
    MarketplaceAlert, 
    Organization, 
    MarketplaceNeed, 
    VolunteerStats, 
    NeedStatus, 
    TelegramMessage, 
    NGO_Campaign,
    MissionTeam,
    CampaignParticipationStatus,
    CampaignStatus
)
from backend.app.services.otp import generate_otp_pair, verify_otp
from backend.app.services.telegram_service import telegram_service
from backend.app.services.ai_service import ai_service
from backend.app.services.media_service import media_service

router = APIRouter()

# --- Helper Functions ---

async def log_telegram_message(db: AsyncSession, chat_id: str, message_id: int):
    """Save message ID to DB for 24h cleanup."""
    try:
        msg = TelegramMessage(chat_id=chat_id, message_id=message_id)
        db.add(msg)
        await db.commit()
    except Exception as e:
        print(f"[ERROR] Failed to log telegram message: {e}")

async def send_and_log(db: AsyncSession, bg: BackgroundTasks, chat_id: str, text: str, **kwargs) -> Optional[int]:
    msg_id = await telegram_service.send_message(chat_id, text, **kwargs)
    if msg_id:
        bg.add_task(log_telegram_message, db, chat_id, msg_id)
    return msg_id

async def process_ai_surplus_report(chat_id: str, text: str, alert_id: int, bg: BackgroundTasks):
    """
    Background Task: Heavy-lifting AI parsing and summary card construction.
    This prevents Telegram webhook timeouts.
    """
    try:
        async with async_session() as db:
            parsed = await ai_service.parse_surplus_text(text)
            if parsed:
                # Check for Fallback notice
                notice = "⚠️ *Plan B: Basic Sync Used (AI Busy)*\n\n" if parsed.get("fallback_used") else "🤖 *AI Summary - Please Confirm*\n\n"
                
                summary = (
                    f"{notice}"
                    f"📦 *Item*: {parsed.get('item', 'N/A')}\n"
                    f"🔢 *Quantity*: {parsed.get('quantity', 'N/A')}\n"
                    f"📍 *Location*: {parsed.get('location', 'N/A')}\n"
                    f"📝 *Notes*: {parsed.get('notes', 'None')}\n\n"
                    f"Is this correct? NGOs will use this to coordinate."
                )
                inline_kb = {
                    "inline_keyboard": [
                        [
                            {"text": "✅ Confirm", "callback_data": f"ai_confirm_{alert_id}"},
                            {"text": "🔄 Edit", "callback_data": f"ai_edit_{alert_id}"}
                        ]
                    ]
                }
                await send_and_log(db=db, bg=bg, chat_id=chat_id, text=summary, reply_markup=inline_kb)
            else:
                await send_and_log(db=db, bg=bg, chat_id=chat_id, text="🙏 *Thank you!* Your report has been received and shared with local NGOs.")
    except Exception as e:
        print(f"[ERROR] Background AI Processing Failed: {e}")

# --- Webhook Endpoint ---

@router.post("/telegram")
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    V2.0 Stability Webhook: Responds immediately and processes heavy AI tasks in the background.
    """
    try:
        data = await request.json()
        
        # --- 1. Handle Callbacks (Inline Buttons) ---
        if "callback_query" in data:
            callback = data["callback_query"]
            chat_id = str(callback["message"]["chat"]["id"])
            data_payload = callback.get("data", "")
            
            stmt = select(Volunteer).where(Volunteer.telegram_chat_id == chat_id)
            volunteer = (await db.execute(stmt)).scalar_one_or_none()
            
            # Marketplace Flow
            if data_payload.startswith("accept_") and volunteer:
                dispatch_id = int(data_payload.split("_")[1])
                stmt = select(MarketplaceDispatch).where(MarketplaceDispatch.id == dispatch_id, MarketplaceDispatch.volunteer_id == volunteer.id)
                dispatch = (await db.execute(stmt)).scalar_one_or_none()
                
                if dispatch and dispatch.status == DispatchStatus.SENT:
                    dispatch.status = DispatchStatus.ACCEPTED
                    raw_code, hashed, expires_at = generate_otp_pair()
                    dispatch.otp_hash = hashed
                    dispatch.otp_expires_at = expires_at
                    await db.commit()
                    
                    await send_and_log(db=db, bg=background_tasks, chat_id=chat_id,
                        text=f"🎫 *Marketplace Mission Confirmed!*\n\nYour Pickup CODE is: `{raw_code}`\nProvide this to the donor once items are collected."
                    )

            # Campaign Flow: Join Pool
            if data_payload.startswith("join_mission_") and volunteer:
                campaign_id = int(data_payload.split("_")[2])
                stmt_check = select(MissionTeam).where(MissionTeam.campaign_id == campaign_id, MissionTeam.volunteer_id == volunteer.id)
                existing = (await db.execute(stmt_check)).scalar_one_or_none()
                if not existing:
                    db.add(MissionTeam(campaign_id=campaign_id, volunteer_id=volunteer.id, status=CampaignParticipationStatus.PENDING))
                    await db.commit()
                    await send_and_log(db=db, bg=background_tasks, chat_id=chat_id, text="✅ *Request Sent!* Waiting for NGO selection.")

            # AI Confirmation Callbacks
            if data_payload.startswith("ai_confirm_"):
                alert_id = int(data_payload.split("_")[2])
                stmt = select(MarketplaceAlert).where(MarketplaceAlert.id == alert_id)
                alert = (await db.execute(stmt)).scalar_one_or_none()
                if alert:
                    alert.is_confirmed = True
                    alert.is_processed = False
                    await db.commit()
                    await send_and_log(db=db, bg=background_tasks, chat_id=chat_id, text="✅ *Report Confirmed!* Your donation is now live for NGOs. ✨🤝")
            
            return {"status": "callback_handled"}

        # --- 2. Handle Text Messages ---
        if "message" not in data: return {"status": "ignored"}
        
        message = data["message"]
        chat_id = str(message["chat"]["id"])
        text = message.get("text", "").strip()
        
        if text == "/start":
            welcome_text = "🤝 *WELCOME TO SAHYOG SETU V2.0*"
            inline_kb = {"inline_keyboard": [[{"text": "🙋 Join as Volunteer", "callback_data": "join_volunteer"}, {"text": "🎁 Donate Surplus", "callback_data": "donate_surplus"}]]}
            await send_and_log(db=db, bg=background_tasks, chat_id=chat_id, text=welcome_text, reply_markup=inline_kb)
            return {"status": "start_sent"}

        # Surplus Reporting (The AI Ingestion Flow)
        if text and not text.startswith("/"):
            # Check for role/context first
            stmt = select(MarketplaceAlert).where(MarketplaceAlert.chat_id == chat_id, MarketplaceAlert.message_body == "[Pending Report]")
            pending = (await db.execute(stmt)).scalar_one_or_none()
            
            if pending:
                pending.message_body = text
                await db.commit()
                # --- Non-Blocking AI Orchestration ---
                await send_and_log(db=db, bg=background_tasks, chat_id=chat_id, text="Analyzing your report... 🤖 (Hold on a sec!)")
                background_tasks.add_task(process_ai_surplus_report, chat_id, text, pending.id, background_tasks)
                return {"status": "ai_task_queued"}

    except Exception as e:
        print(f"[ERROR] Webhook Failed: {e}")
        return {"status": "error"}

    return {"status": "ignored"}

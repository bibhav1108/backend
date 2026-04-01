from fastapi import APIRouter, Depends, Request, BackgroundTasks
import os
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

router = APIRouter()

# --- Shared Assets ---
STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "static")
WELCOME_PHOTO_PATH = os.path.join(STATIC_DIR, "welcome.png")

# --- Helper Functions ---

async def log_telegram_message(chat_id: str, message_id: int):
    """
    Save message ID to DB for 24h cleanup.
    Self-contained session for background execution safety.
    """
    try:
        async with async_session() as db:
            msg = TelegramMessage(chat_id=chat_id, message_id=message_id)
            db.add(msg)
            await db.commit()
    except Exception as e:
        print(f"[ERROR] Failed to log telegram message: {e}")

async def send_and_log(bg: BackgroundTasks, chat_id: str, text: str, **kwargs) -> Optional[int]:
    """Sends a Telegram message and queues its ID for cleanup in the background."""
    msg_id = await telegram_service.send_message(chat_id, text, **kwargs)
    if msg_id:
        bg.add_task(log_telegram_message, chat_id, msg_id)
    return msg_id

async def send_photo_and_log(bg: BackgroundTasks, chat_id: str, photo_url: str, caption: str, **kwargs) -> Optional[int]:
    """Sends a Telegram photo and queues its ID for cleanup in the background."""
    msg_id = await telegram_service.send_photo(chat_id, photo_url, caption, **kwargs)
    if msg_id:
        bg.add_task(log_telegram_message, chat_id, msg_id)
    return msg_id

async def process_ai_surplus_report(chat_id: str, text: str, alert_id: int):
    """
    Background Task: Heavy-lifting AI parsing and summary card construction.
    This prevents Telegram webhook timeouts.
    """
    print(f"[TRACE] Starting AI Processing for Chat: {chat_id} | Alert: {alert_id}")
    try:
        async with async_session() as db:
            print(f"[TRACE] Invoking Gemini Parser for: {text[:20]}...")
            parsed = await ai_service.parse_surplus_text(text)
            print(f"[TRACE] Gemini Response Received: {parsed is not None} | Type: {type(parsed)}")
            
            # --- Normalize AI Output (Handle Lists from Gemini) ---
            if isinstance(parsed, list) and len(parsed) > 0:
                print(f"[TRACE] Multiple items detected. Consolidating list.")
                # Combine multiple items into a single summary for display
                all_items = []
                all_qties = []
                for p in parsed:
                    if isinstance(p, dict):
                        # Use get() for safety
                        all_items.append(str(p.get("item", "N/A")))
                        all_qties.append(str(p.get("quantity", "N/A")))
                
                # Take the first item as base (for location/notes) and override item/qty fields
                consolidated = parsed[0].copy() if isinstance(parsed[0], dict) else {}
                consolidated["item"] = ", ".join(all_items)
                consolidated["quantity"] = ", ".join(all_qties)
                parsed = consolidated
            
            # Safety check to prevent AttributeError
            if not isinstance(parsed, dict):
                print(f"[TRACE] Final response is not a dictionary. Discarding.")
                parsed = None

            # --- Filtering Logic: Ignore empty/garbage reports ---
            if not parsed or not parsed.get("item") or str(parsed.get("item")).lower() in ["n/a", "donation item"]:
                print(f"[TRACE] Discarding garbage/empty report.")
                # Delete the alert from DB to keep the dashboard clean
                stmt_del = delete(MarketplaceAlert).where(MarketplaceAlert.id == alert_id)
                await db.execute(stmt_del)
                await db.commit()
                
                # Feedback to user
                missing_msg = (
                    "🙏 *We missed some details!*\n\n"
                    "Please send us the details like this:\n"
                    "`[Item Name] [Quantity] [Location]`\n\n"
                    "Example: `10kg Dal and Rice at Sector 62, Noida` ✨"
                )
                await telegram_service.send_message(chat_id, missing_msg)
                return

            if parsed:
                # Check for Fallback notice
                notice = "⚠️ *Plan B: Basic Sync Used (AI Busy)*\n\n" if parsed.get("fallback_used") else "🤖 *Summary - Please Confirm*\n\n"
                
                summary = (
                    f"{notice}"
                    f"📦 *Item*: {parsed.get('item', 'N/A')}\n"
                    f"🔢 *Quantity*: {parsed.get('quantity', 'N/A')}\n"
                    f"📍 *Location*: {parsed.get('location', 'N/A')}\n"
                    f"📝 *Notes*: {parsed.get('notes', 'None')}\n\n"
                    f"✨ *Is this correct?* Confirming will help local NGOs reach you faster."
                )
                inline_kb = {
                    "inline_keyboard": [
                        [
                            {"text": "✅ Yes, Confirm", "callback_data": f"ai_confirm_{alert_id}"},
                            {"text": "🔄 No, Edit", "callback_data": f"ai_edit_{alert_id}"}
                        ]
                    ]
                }
                print(f"[TRACE] Sending AI Summary Card to Telegram.")
                res_id = await telegram_service.send_message(chat_id, summary, reply_markup=inline_kb)
                print(f"[TRACE] Final Summary Card Dispatch Result: {res_id is not None}")
                
                if res_id is None:
                    # Retry with plain text (No Markdown) if it failed (likely a parsing error)
                    print(f"[TRACE] Retrying with plain text fallback...")
                    plain_summary = summary.replace("*", "").replace("_", "")
                    await telegram_service.send_message(chat_id, plain_summary, reply_markup=inline_kb, parse_mode=None)
            else:
                await telegram_service.send_message(chat_id, "🙏 *Thank you!* Your report has been shared. Our team will review and connect with you shortly.")
    except Exception as e:
        print(f"[ERROR] Background AI Processing Failed: {e}")
        traceback.print_exc()

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
            callback_query_id = callback["id"]
            chat_id = str(callback["message"]["chat"]["id"])
            data_payload = callback.get("data", "")
            
            # 1.1 Acknowledge all callbacks immediately to stop button "spinning"
            await telegram_service.answer_callback_query(callback_query_id)
            print(f"[TRACE] Callback Received: {data_payload} from Chat: {chat_id}")

            stmt = select(Volunteer).where(Volunteer.telegram_chat_id == chat_id)
            volunteer = (await db.execute(stmt)).scalar_one_or_none()
            
            # Marketplace Flow
            if data_payload.startswith("accept_"):
                dispatch_id = int(data_payload.split("_")[1])
                print(f"[TRACE] Volunteer Attempting Acceptance. Dispatch: {dispatch_id} | Vol Found: {volunteer is not None}")
                
                if not volunteer:
                    await send_and_log(bg=background_tasks, chat_id=chat_id, text="⚠️ *Error*: You must be a registered volunteer to accept missions.")
                    return {"status": "unregistered"}

                stmt = select(MarketplaceDispatch).where(MarketplaceDispatch.id == dispatch_id, MarketplaceDispatch.volunteer_id == volunteer.id)
                dispatch = (await db.execute(stmt)).scalar_one_or_none()
                
                print(f"[TRACE] Dispatch Record Found: {dispatch is not None}")
                if dispatch and dispatch.status == DispatchStatus.SENT:
                    dispatch.status = DispatchStatus.ACCEPTED
                    raw_code, hashed, expires_at = generate_otp_pair()
                    dispatch.otp_hash = hashed
                    dispatch.otp_expires_at = expires_at
                    await db.commit()
                    
                    print(f"[TRACE] Dispatch Status Updated to ACCEPTED. OTP Generated.")
                    await send_and_log(bg=background_tasks, chat_id=chat_id,
                        text=f"🎫 *Mission Accepted!*\n\nYour Pickup CODE is: `{raw_code}`\n\nShow this code to the donor upon collection. Thank you for your service! 🤝"
                    )
                elif dispatch:
                    print(f"[TRACE] Acceptance Refused: Dispatch already in status {dispatch.status}")

            # Campaign Flow: Join Pool
            if data_payload.startswith("join_mission_") and volunteer:
                campaign_id = int(data_payload.split("_")[2])
                stmt_check = select(MissionTeam).where(MissionTeam.campaign_id == campaign_id, MissionTeam.volunteer_id == volunteer.id)
                existing = (await db.execute(stmt_check)).scalar_one_or_none()
                if not existing:
                    db.add(MissionTeam(campaign_id=campaign_id, volunteer_id=volunteer.id, status=CampaignParticipationStatus.PENDING))
                    await db.commit()
                    await send_and_log(bg=background_tasks, chat_id=chat_id, text="✅ *Request Received!* The NGO team is reviewing your profile. Stay tuned! 🕒")
            
            # --- Added Flows: Join & Donate ---
            if data_payload == "donate_surplus":
                # Create a placeholder alert to capture the next message
                alert = MarketplaceAlert(chat_id=chat_id, message_body="[Pending Report]")
                db.add(alert)
                await db.commit()
                
                format_msg = (
                    "🎁 *Tell us about the food!*\n\n"
                    "Please send us the details like this:\n"
                    "`[Item Name] [Quantity] [Location]`\n\n"
                    "Example: `10kg Dal and Rice at Sector 62, Noida` ✨"
                )
                await send_and_log(bg=background_tasks, chat_id=chat_id, text=format_msg)

            if data_payload == "join_volunteer":
                stmt = select(Volunteer).where(Volunteer.telegram_chat_id == chat_id)
                existing = (await db.execute(stmt)).scalar_one_or_none()
                
                if existing:
                    await send_and_log(bg=background_tasks, chat_id=chat_id, text="✅ *You are already a registered volunteer!* Use /menu to see active missions.")
                else:
                    onboard_msg = "🦁 *Onboarding Started!*\n\nTo join our mission, we need to verify your contact. Please share your phone number using the button below."
                    reply_kb = {
                        "keyboard": [[{"text": "📱 Share Contact", "request_contact": True}]],
                        "resize_keyboard": True,
                        "one_time_keyboard": True
                    }
                    await send_and_log(bg=background_tasks, chat_id=chat_id, text=onboard_msg, reply_markup=reply_kb)

            # --- AI Confirmation & Edit Handlers ---
            if data_payload.startswith("ai_confirm_"):
                alert_id = int(data_payload.split("_")[2])
                stmt = select(MarketplaceAlert).where(MarketplaceAlert.id == alert_id)
                alert = (await db.execute(stmt)).scalar_one_or_none()
                if alert:
                    alert.is_confirmed = True
                    alert.is_processed = False
                    await db.commit()
                    await send_and_log(bg=background_tasks, chat_id=chat_id, text="✅ *Report Verified!* Your donation is now live and waiting for a hero. ✨🤝")

            if data_payload.startswith("ai_edit_"):
                alert_id = int(data_payload.split("_")[2])
                stmt = select(MarketplaceAlert).where(MarketplaceAlert.id == alert_id)
                alert = (await db.execute(stmt)).scalar_one_or_none()
                if alert:
                    # Allow user to re-enter description by resetting status
                    alert.message_body = "[Pending Report]"
                    await db.commit()
                    await send_and_log(bg=background_tasks, chat_id=chat_id, text="🔄 *No problem!* Just send me the corrected details (Item, Qty, Location) and I'll re-analyze them.")
            
            return {"status": "callback_handled"}

        # --- 2. Handle Text Messages ---
        if "message" not in data: return {"status": "ignored"}
        
        message = data["message"]
        chat_id = str(message["chat"]["id"])
        text = message.get("text", "").strip()
        contact = message.get("contact")

        # --- Handle Shared Contact (Registration) ---
        if contact:
            phone = contact.get("phone_number")
            name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip() or "Volunteer"
            
            # Use first organization as default for now
            stmt_org = select(Organization).limit(1)
            org = (await db.execute(stmt_org)).scalar_one_or_none()
            org_id = org.id if org else 1

            # Check if user exists by phone
            stmt_check = select(Volunteer).where(Volunteer.phone_number == phone)
            v = (await db.execute(stmt_check)).scalar_one_or_none()
            
            if v:
                v.telegram_chat_id = chat_id
                v.telegram_active = True
            else:
                v = Volunteer(
                    org_id=org_id,
                    name=name,
                    phone_number=phone,
                    telegram_chat_id=chat_id,
                    telegram_active=True
                )
                db.add(v)
            
            await db.commit()
            await send_and_log(bg=background_tasks, chat_id=chat_id, text=f"🎉 *Welcome {name}!* Your registration is complete. You will now receive mission alerts for your area! 🚀")
            return {"status": "registered"}

        if text == "/start":
            welcome_text = "🤝 *WELCOME TO SAHYOGSYNC*\n\nWe connect extra food to people who need it. How can we help you today? 🌍"
            inline_kb = {"inline_keyboard": [[{"text": "🙋 Join Volunteer", "callback_data": "join_volunteer"}, {"text": "🎁 Donate Food", "callback_data": "donate_surplus"}]]}
            
            # --- Fail-Safe Experience ---
            # Try to send the local poster first
            msg_id = await send_photo_and_log(bg=background_tasks, chat_id=chat_id, photo_url=WELCOME_PHOTO_PATH, caption=welcome_text, reply_markup=inline_kb)
            
            # If photo fails (e.g. file missing or API error), fallback to text-only
            if not msg_id:
                await send_and_log(bg=background_tasks, chat_id=chat_id, text=welcome_text, reply_markup=inline_kb)
                
            return {"status": "start_sent"}
            

        # Surplus Reporting (The AI Ingestion Flow)
        if text and not text.startswith("/"):
            # Check for role/context first - limit(1) to prevent MultipleResultsFound error
            stmt = (
                select(MarketplaceAlert)
                .where(MarketplaceAlert.chat_id == chat_id, MarketplaceAlert.message_body == "[Pending Report]")
                .order_by(desc(MarketplaceAlert.created_at))
                .limit(1)
            )
            pending = (await db.execute(stmt)).scalar_one_or_none()
            
            if pending:
                pending.message_body = text
                await db.commit()
                # --- Non-Blocking AI Orchestration ---
                print(f"[TRACE] Handing over to Background Task for Chat: {chat_id}")
                await send_and_log(bg=background_tasks, chat_id=chat_id, text="🤖 *Thinking...* Analyzing your report details now!")
                background_tasks.add_task(process_ai_surplus_report, chat_id, text, pending.id)
                print(f"[TRACE] Background task queued successfully for Alert: {pending.id}")
                return {"status": "ai_task_queued"}

    except Exception as e:
        print(f"[ERROR] Webhook Failed: {e}")
        return {"status": "error"}

    return {"status": "ignored"}

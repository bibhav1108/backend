from fastapi import APIRouter, Depends, Request, BackgroundTasks
import os
import traceback
from typing import Optional
from datetime import datetime, timedelta, timezone
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
    CampaignStatus,
    MarketplaceInventory,
    InboundMessage,
    User,
    UserRole,
    VolunteerStatus
)
from backend.app.api.volunteers.service import onboard_volunteer_via_telegram
from backend.app.services.otp import generate_otp_pair, verify_otp
from backend.app.services.telegram_service import telegram_service
from backend.app.services.ai_service import ai_service
from backend.app.notifications.service import notification_service
import random
import string

router = APIRouter()

# --- Shared Assets ---
STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "static")
WELCOME_PHOTO_PATH = os.path.join(STATIC_DIR, "welcome.png")

# --- Helper Functions ---

def normalize_phone(phone: str) -> str:
    """
    Standardizes phone numbers for matching.
    Removes +, 91, 0, and any non-digit characters. 
    Returns the last 10 digits for Indian numbers.
    """
    if not phone: return ""
    digits = "".join(filter(str.isdigit, phone))
    # If it's a typical Indian number with country code (91XXXXXXXXXX), take last 10
    if len(digits) >= 10:
        return digits[-10:]
    return digits

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
            
            # --- Normalize AI Output (Handle Nested Lists or Direct Lists) ---
            if isinstance(parsed, dict):
                # Check for common nested keys from Gemini
                for key in ["donations", "items", "reports"]:
                    if key in parsed and isinstance(parsed[key], list):
                        parsed = parsed[key]
                        break

            if isinstance(parsed, list) and len(parsed) > 0:
                print(f"[TRACE] Multiple items detected. Consolidating list.")
                all_items = []
                all_qties = []
                locs = []
                notes = []
                for p in parsed:
                    if isinstance(p, dict):
                        # Extract and cleaning N/A values
                        item = p.get("item", "N/A")
                        qty = p.get("quantity", "N/A")
                        loc = p.get("location", "N/A")
                        note = p.get("notes", "N/A")
                        
                        if item != "N/A": all_items.append(str(item))
                        if qty != "N/A": all_qties.append(str(qty))
                        if loc != "N/A": locs.append(str(loc))
                        if note != "N/A": notes.append(str(note))
                
                # Consolidate into a single flat dict for the bot card
                # Using dict.fromkeys to keep unique values while maintaining order
                parsed = {
                    "item": ", ".join(dict.fromkeys(all_items)) or "Donation Item",
                    "quantity": ", ".join(all_qties) or "N/A",
                    "location": ", ".join(dict.fromkeys(locs)) or "N/A",
                    "notes": "; ".join(dict.fromkeys(notes)) or "N/A"
                }
            
            # Final safety check to prevent downstream AttributeError
            if not isinstance(parsed, dict):
                print(f"[TRACE] Final normalized response is not a dictionary. Discarding.")
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

            if isinstance(parsed, dict):
                # Save predictions to the alert record for better conversion
                stmt_updt = select(MarketplaceAlert).where(MarketplaceAlert.id == alert_id)
                alert = (await db.execute(stmt_updt)).scalar_one_or_none()
                
                if alert:
                    alert.item = parsed.get("item", "N/A")
                    alert.quantity = parsed.get("quantity", "N/A")
                    alert.location = parsed.get("location", "N/A")
                    alert.notes = parsed.get("notes", "N/A")
                    
                    # Store Enums if valid
                    try:
                        cat = parsed.get("category", "OTHER").upper()
                        if cat in ["FOOD", "WATER", "KIT", "BLANKET", "MEDICAL", "VEHICLE", "OTHER"]:
                            alert.predicted_type = cat
                        
                        urg = parsed.get("urgency", "MEDIUM").upper()
                        if urg in ["LOW", "MEDIUM", "HIGH"]:
                            alert.predicted_urgency = urg
                    except:
                        pass
                    
                    await db.commit()

                # Check for Fallback notice
                notice = "⚠️ *Plan B: Basic Sync Used (AI Busy)*\n\n" if parsed.get("fallback_used") else "🤖 *Summary - Please Confirm*\n\n"
                
                summary = (
                    f"{notice}"
                    f"📦 *Item*: {parsed.get('item', 'N/A')}\n"
                    f"🔢 *Quantity*: {parsed.get('quantity', 'N/A')}\n"
                    f"📍 *Location*: {parsed.get('location', 'N/A')}\n"
                    f"🏷️ *Category*: {parsed.get('category', 'OTHER')}\n"
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
        
        chat_id = data.get("message", {}).get("chat", {}).get("id") or \
                  data.get("callback_query", {}).get("from", {}).get("id")
        
        message_id = data.get("message", {}).get("message_id") or \
                     data.get("callback_query", {}).get("message", {}).get("message_id")

        if not chat_id or not message_id:
            return {"status": "invalid_update"}
        
        # --- Deduplication Guard ---
        # Checks if this specific message from this chat has already been handled.
        stmt_dup = select(InboundMessage).where(
            InboundMessage.chat_id == str(chat_id), 
            InboundMessage.message_id == message_id
        )
        existing = (await db.execute(stmt_dup)).scalar_one_or_none()
        if existing:
            print(f"[DEDUPE] Ignoring duplicate message {message_id} from {chat_id}")
            return {"status": "duplicate_ignored"}
        
        # Log it as processed before continuing
        new_inbound = InboundMessage(chat_id=str(chat_id), message_id=message_id)
        db.add(new_inbound)
        await db.commit()

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

                # 1. Fetch dispatch with relation to check mission status
                stmt = select(MarketplaceDispatch).where(
                    MarketplaceDispatch.id == dispatch_id
                ).options(selectinload(MarketplaceDispatch.marketplace_need))
                dispatch = (await db.execute(stmt)).scalar_one_or_none()
                
                if not dispatch:
                    await send_and_log(bg=background_tasks, chat_id=chat_id, text="⚠️ *Error*: Mission record not found.")
                    return {"status": "error"}

                # 2. FCFS CHECK: Is the mission already taken?
                # A mission is taken if: 
                # - The Need status is COMPLETED
                # - Another Dispatch for the same Need is already ACCEPTED
                stmt_check = select(MarketplaceDispatch).where(
                    MarketplaceDispatch.marketplace_need_id == dispatch.marketplace_need_id,
                    MarketplaceDispatch.status == DispatchStatus.ACCEPTED
                )
                any_accepted = (await db.execute(stmt_check)).scalar_one_or_none()

                if any_accepted or dispatch.marketplace_need.status == NeedStatus.COMPLETED:
                    print(f"[TRACE] FCFS Conflict: Mission {dispatch.marketplace_need_id} already claimed.")
                    await send_and_log(bg=background_tasks, chat_id=chat_id, 
                        text="🏃‍♂️ *Mission Already Taken!*\n\nHero, you were just a second too late! Another volunteer has already claimed this pickup. Thank you for your readiness! 🦸‍♂️"
                    )
                    return {"status": "already_taken"}

                # 3. Success: Claim the mission
                if dispatch.status == DispatchStatus.SENT:
                    dispatch.status = DispatchStatus.ACCEPTED
                    raw_code, hashed, expires_at = generate_otp_pair()
                    dispatch.otp_hash = hashed
                    dispatch.otp_expires_at = expires_at
                    
                    # Ensure Need status is DISPATCHED
                    dispatch.marketplace_need.status = NeedStatus.DISPATCHED
                    
                    # 🔴 STATUS SYNC: Set volunteer to ON_MISSION
                    volunteer.status = VolunteerStatus.ON_MISSION
                    
                    await db.commit()
                    
                    print(f"[TRACE] FCFS Success: {chat_id} claimed mission {dispatch_id}")
                    # Navigation Link
                    nav_link = ""
                    if dispatch.marketplace_need.latitude and dispatch.marketplace_need.longitude:
                        lat, lng = dispatch.marketplace_need.latitude, dispatch.marketplace_need.longitude
                        nav_link = f"\n\n📍 *Navigation*: [Open Google Maps](https://www.google.com/maps/search/?api=1&query={lat},{lng})"

                    await send_and_log(bg=background_tasks, chat_id=chat_id,
                        text=f"🎫 *Mission Accepted!*\n\nYour Pickup CODE is: `{raw_code}`{nav_link}\n\nShow this code to the donor upon collection. Thank you for your service! 🤝"
                    )

                    # --- Notification Center: Mission Accepted ---
                    await notification_service.notify_mission_accepted(
                        db=db,
                        org_id=volunteer.org_id,
                        volunteer_name=volunteer.name,
                        mission_name=dispatch.marketplace_need.type.name,
                        dispatch_id=dispatch.id
                    )

                    # --- Notify Donor ---
                    try:
                        # Fetch donor chat_id via Alert
                        stmt_alert = select(MarketplaceAlert.chat_id).join(MarketplaceNeed).where(MarketplaceNeed.id == dispatch.marketplace_need_id)
                        donor_chat_id = (await db.execute(stmt_alert)).scalar()

                        if donor_chat_id:
                            donor_msg = (
                                f"🌟 *Wonderful News!* \n\n"
                                f"Our dedicated volunteer, *{volunteer.name}*, is on their way to collect your generous donation! 🤝 \n\n"
                                f"Once they arrive, they will share a *6-digit Pickup CODE* with you. Please click the button below to verify the collection."
                            )
                            donor_kb = {
                                "inline_keyboard": [[
                                    {"text": "✅ Confirm OTP", "callback_data": f"prompt_otp_{dispatch_id}"}
                                ]]
                            }
                            await telegram_service.send_message(chat_id=donor_chat_id, text=donor_msg, reply_markup=donor_kb)
                    except Exception as e:
                        print(f"[ERROR] Failed to notify donor: {e}")
                else:
                    print(f"[TRACE] Acceptance Refused: Dispatch already in status {dispatch.status}")

            if data_payload.startswith("decline_"):
                dispatch_id = int(data_payload.split("_")[1])
                stmt = select(MarketplaceDispatch).where(MarketplaceDispatch.id == dispatch_id)
                dispatch = (await db.execute(stmt)).scalar_one_or_none()
                if dispatch and dispatch.status == DispatchStatus.SENT:
                    dispatch.status = DispatchStatus.FAILED # Or add REJECTED status
                    
                    # 🟢 STATUS SYNC: Revert volunteer to AVAILABLE
                    volunteer.status = VolunteerStatus.AVAILABLE
                    
                    await db.commit()
                    await send_and_log(bg=background_tasks, chat_id=chat_id, text="🙏 *No problem!* We've updated the mission status. Thank you for letting us know! ✨")

            # Campaign Flow: Legacy Join Pool (Redirect to Web)
            if data_payload.startswith("join_mission_") and volunteer:
                await send_and_log(bg=background_tasks, chat_id=chat_id, text="🚀 *New Mission Flow!*\n\nWe have upgraded our mission briefing experience. Please use the *dynamic link* sent in the latest broadcast to join your team. See you there!")
            
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
                    
                    # Link to the NEW Public Map Picker
                    loc_picker_url = f"https://sahyog-setu-frontend.vercel.app/alert-location/{alert_id}"
                    
                    loc_request_kb = {
                        "inline_keyboard": [
                            [{"text": "🗺️ Pick Precise Spot on Map", "url": loc_picker_url}],
                            [{"text": "📍 Quick Share (Current Location)", "callback_data": f"prompt_native_loc_{alert_id}"}]
                        ]
                    }
                    await send_and_log(bg=background_tasks, chat_id=chat_id, 
                        text="✅ *Report Verified!* Your donation is now live.\n\n🌟 *Final Step*: To help our volunteers reach you accurately, please pin your exact pickup spot on the map! 👇",
                        reply_markup=loc_request_kb
                    )
                    
                    # --- Notification Center: New Donor Alert ---
                    await notification_service.notify_donor_alert(
                        db=db,
                        alert_id=alert.id,
                        item=alert.item or "Potential Surplus",
                        location=alert.location or "See contacts"
                    )
                    await db.commit()

            if data_payload.startswith("ai_edit_"):
                alert_id = int(data_payload.split("_")[2])
                stmt = select(MarketplaceAlert).where(MarketplaceAlert.id == alert_id)
                alert = (await db.execute(stmt)).scalar_one_or_none()
                if alert:
                    # Allow user to re-enter description by resetting status
                    alert.message_body = "[Pending Report]"
                    await db.commit()
                    await send_and_log(bg=background_tasks, chat_id=chat_id, text="🔄 *No problem!* Just send me the corrected details (Item, Qty, Location) and I'll re-analyze them.")

            if data_payload.startswith("prompt_native_loc_"):
                # Trigger the ReplyKeyboardMarkup for location
                loc_kb = {
                    "keyboard": [[{"text": "📍 Share My Location", "request_location": True}]],
                    "resize_keyboard": True,
                    "one_time_keyboard": True
                }
                await send_and_log(bg=background_tasks, chat_id=chat_id, 
                    text="📍 *Ready!* Please click the button below to share your current location data with us.",
                    reply_markup=loc_kb
                )

            # --- Donor Prompt Handler ---
            if data_payload.startswith("prompt_otp_"):
                dispatch_id = int(data_payload.split("_")[2])
                try:
                    # Verify dispatch belongs to this donor
                    stmt_v = select(MarketplaceDispatch).join(MarketplaceNeed).join(MarketplaceAlert).where(
                        MarketplaceDispatch.id == dispatch_id,
                        MarketplaceAlert.chat_id == chat_id
                    )
                    dispatch = (await db.execute(stmt_v)).scalar_one_or_none()
                    
                    if not dispatch:
                         await send_and_log(bg=background_tasks, chat_id=chat_id, text="⚠️ *Error*: Mission record not found or inaccessible.")
                    elif dispatch.status != DispatchStatus.ACCEPTED:
                         await send_and_log(bg=background_tasks, chat_id=chat_id, text="⏳ *Wait for Volunteer*: Please wait for the volunteer to reach your location and share the code! 🦸‍♂️")
                    else:
                        prompt_msg = "✍️ *Action Required*: Please type the 6-digit code shown by the volunteer now to complete the mission! 🤝"
                        await send_and_log(bg=background_tasks, chat_id=chat_id, text=prompt_msg)
                except Exception as e:
                    print(f"[ERROR] Prompt OTP Handler Failed: {e}")
                    await send_and_log(bg=background_tasks, chat_id=chat_id, text="⚠️ *Error*: Unable to process request. Please try again later.")
            
            return {"status": "callback_handled"}

        # --- 2. Handle Text Messages ---
        if "message" not in data: return {"status": "ignored"}
        
        message = data["message"]
        chat_id = str(message["chat"]["id"])
        text = message.get("text", "").strip()
        contact = message.get("contact")
        location = message.get("location")

        # --- Handle Shared Location ---
        if location:
            lat = location.get("latitude")
            lng = location.get("longitude")
            print(f"[TRACE] Location Received from {chat_id}: {lat}, {lng}")
            
            # Find recent alert for this user that doesn't have coordinates
            stmt_alt = select(MarketplaceAlert).where(
                MarketplaceAlert.chat_id == chat_id
            ).order_by(MarketplaceAlert.created_at.desc()).limit(1)
            alert = (await db.execute(stmt_alt)).scalar_one_or_none()
            
            if alert:
                alert.latitude = lat
                alert.longitude = lng
                await db.commit()
                await send_and_log(bg=background_tasks, chat_id=chat_id, text="📍 *Location Linked!* Thank you! This helps our heroes find the pickup spot faster. 🦸‍♂️")
                return {"status": "location_recorded"}
            return {"status": "location_ignored_no_alert"}

        # --- Handle Shared Contact (Strict Verification) ---
        if contact:
            raw_phone = contact.get("phone_number")
            norm_phone = normalize_phone(raw_phone)
            
            print(f"[TRACE] Verifying Contact: {raw_phone} -> Normalized: {norm_phone}")
            
            # Delegate to Volunteer Service
            creds = await onboard_volunteer_via_telegram(db, norm_phone, chat_id)
            
            if creds:
                if creds.get("already_active"):
                    welcome_msg = (
                        f"✅ *Account Already Linked!*\n\n"
                        f"Welcome back, *{creds['name']}*! Your Telegram is already linked to your SahyogSync account.\n\n"
                        f"👤 *Username*: `{creds['username']}`\n\n"
                        f"You can now use `/menu` to explore active missions. If you've forgotten your password, please use the 'Forgot Password' link on our website. 🚀"
                    )
                else:
                    welcome_msg = (
                        f"🎉 *Verification Successful!*\n\n"
                        f"Welcome to the team, *{creds['name']}*! A new volunteer account has been created for you.\n\n"
                        f"👤 *Username*: `{creds['username']}`\n"
                        f"🔐 *Password*: `{creds['password']}`\n\n"
                        f"Please log in to the SahyogSync portal to complete your profile and start helping! 🚀"
                    )
                await send_and_log(bg=background_tasks, chat_id=chat_id, text=welcome_msg)
                return {"status": "verified"}
            else:
                reject_msg = (
                    "⚠️ *Access Denied*\n\n"
                    f"The number `{raw_phone}` is not registered in our NGO dashboard.\n\n"
                    "Please contact your NGO Coordinator to get your number added first. Thank you! 🙏"
                )
                await send_and_log(bg=background_tasks, chat_id=chat_id, text=reject_msg)
                return {"status": "rejected"}

        if text == "/start" or text == "/menu":
            welcome_text = "🤝 *WELCOME TO SAHYOGSYNC*\n\nWe connect extra food to people who need it. How can we help you today? 🌍"
            inline_kb = {"inline_keyboard": [[{"text": "🙋 Join Volunteer", "callback_data": "join_volunteer"}, {"text": "🎁 Donate Food", "callback_data": "donate_surplus"}]]}
            
            # --- Fail-Safe Experience ---
            # Try to send the local poster first
            msg_id = await send_photo_and_log(bg=background_tasks, chat_id=chat_id, photo_url=WELCOME_PHOTO_PATH, caption=welcome_text, reply_markup=inline_kb)
            
            # If photo fails (e.g. file missing or API error), fallback to text-only
            if not msg_id:
                await send_and_log(bg=background_tasks, chat_id=chat_id, text=welcome_text, reply_markup=inline_kb)
            return {"status": "start_sent"}

        if text == "/donate":
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
            return {"status": "donate_started"}

        if text == "/help":
            help_msg = (
                "🤖 **SahyogSync Help Center**\n\n"
                "---\n\n"
                "📜 **Commands & Usage**\n\n"
                "/start → Start the bot & Main Menu\n"
                "/help → Open help section\n"
                "/tutorial → View step-by-step guide\n"
                "/donate → Contribute resources\n\n"
                "👤 **Volunteer Task List**\n"
                "/my_missions → Donation Pickups (Speed Layer)\n"
                "/my_campaigns → Mass Missions (NGO Initiatives)\n"
                "/cancel → Cancel active pickup\n\n"
                "/about → Learn about SahyogSync\n\n"
                "---\n\n"
                "📞 **Customer Support**\n\n"
                "For any issues or assistance:\n\n"
                "📧 Email: [i.e.ishantiwari@gmail.com](mailto:i.e.ishantiwari@gmail.com)\n"
                "📱 Telegram: @Ishantiwariii\n"
                "🕒 Response Time: Within 24 hours\n\n"
                "---\n\n"
                "Thank you for using SahyogSync."
            )
            await send_and_log(bg=background_tasks, chat_id=chat_id, text=help_msg)
            return {"status": "help_sent"}

        if text == "/tutorial":
            tutorial_msg = (
                "📘 **SahyogSync Tutorial**\n\n"
                "Follow these simple steps to get started:\n\n"
                "---\n\n"
                "1️⃣ **Start the Bot**\n"
                "Use /start to begin and open the main menu.\n\n"
                "2️⃣ **Select Your Role**\n"
                "Choose whether you are a Volunteer or a Donor.\n\n"
                "3️⃣ **Choose an Action**\n"
                "• Donate extra food resources\n"
                "• Join as a Volunteer for missions\n\n"
                "4️⃣ **Provide Details**\n"
                "Enter required information like item details and your location.\n\n"
                "5️⃣ **Submit & Track**\n"
                "Submit your report and use `/my_missions` for pickups or `/my_campaigns` for mass missions.\n\n"
                "---\n\n"
                "💡 Tip: Use the menu buttons for faster and easier navigation.\n\n"
                "---\n\n"
                "You're all set to use SahyogSync 🚀"
            )
            await send_and_log(bg=background_tasks, chat_id=chat_id, text=tutorial_msg)
            return {"status": "tutorial_sent"}

        if text == "/about":
            about_msg = (
                "ℹ️ **About SahyogSync**\n\n"
                "SahyogSync is a smart platform designed to connect NGOs, volunteers, and donors for efficient resource allocation and support.\n\n"
                "Our goal is to ensure that the right help reaches the right place at the right time by streamlining requests, managing resources, and enabling real-time coordination.\n\n"
                "Key Features:\n"
                "• Request and track assistance\n"
                "• Volunteer task management\n"
                "• Donation and resource coordination\n"
                "• Real-time updates and transparency\n\n"
                "---\n\n"
                "“Powering the Right Help, at the Right Time.”"
            )
            await send_and_log(bg=background_tasks, chat_id=chat_id, text=about_msg)
            return {"status": "about_sent"}

        if text == "/my_missions":
            # Identify volunteer
            stmt_v = select(Volunteer).where(Volunteer.telegram_chat_id == chat_id)
            volunteer = (await db.execute(stmt_v)).scalar_one_or_none()
            
            if not volunteer:
                await send_and_log(bg=background_tasks, chat_id=chat_id, text="⚠️ *Not Registered*: Use /start to join as a volunteer first!")
                return {"status": "unregistered"}

            # Fetch active dispatches
            stmt_m = (
                select(MarketplaceDispatch)
                .join(MarketplaceNeed, MarketplaceDispatch.marketplace_need_id == MarketplaceNeed.id)
                .where(MarketplaceDispatch.volunteer_id == volunteer.id, MarketplaceDispatch.status == DispatchStatus.ACCEPTED)
            )
            active = (await db.execute(stmt_m)).scalars().all()
            
            if not active:
                await send_and_log(bg=background_tasks, chat_id=chat_id, text="🌟 *No Active Missions*: You're all caught up! Use /menu to find how you can help.")
            else:
                missions_text = "👤 *Your Active Missions*:\n\n"
                for i, d in enumerate(active, 1):
                    nav_link = ""
                    if d.marketplace_need.latitude and d.marketplace_need.longitude:
                        lat, lng = d.marketplace_need.latitude, d.marketplace_need.longitude
                        nav_link = f" ([View Map](https://www.google.com/maps/search/?api=1&query={lat},{lng}))"
                    
                    missions_text += f"{i}. Protocol READY for pickup at *{d.marketplace_need.pickup_address}*{nav_link}.\n"
                missions_text += "\nShow your 6-digit code to the donor upon arrival!"
                await send_and_log(bg=background_tasks, chat_id=chat_id, text=missions_text)
            return {"status": "missions_sent"}

        if text == "/my_campaigns":
            # Identify volunteer
            stmt_v = select(Volunteer).where(Volunteer.telegram_chat_id == chat_id)
            volunteer = (await db.execute(stmt_v)).scalar_one_or_none()
            
            if not volunteer:
                await send_and_log(bg=background_tasks, chat_id=chat_id, text="⚠️ *Not Registered*: Join as a volunteer first to see your campaigns.")
                return {"status": "unregistered"}

            # Fetch joined campaigns (Pending/Approved/Rejected)
            stmt_c = (
                select(MissionTeam)
                .options(selectinload(MissionTeam.campaign))
                .where(MissionTeam.volunteer_id == volunteer.id)
                .order_by(MissionTeam.joined_at.desc())
            )
            participations = (await db.execute(stmt_c)).scalars().all()
            
            if not participations:
                await send_and_log(bg=background_tasks, chat_id=chat_id, text="ℹ️ *No Campaigns*: You haven't joined any mass missions yet. Watch for broadcasts! 📢")
            else:
                campaign_msg = "🎭 *Your Mass Missions (Campaigns)*\n\n"
                base_url = "https://sahyog-setu-frontend.vercel.app/missions"
                for p in participations:
                    status_icon = "✅" if p.status == CampaignParticipationStatus.APPROVED else "⏳"
                    if p.status == CampaignParticipationStatus.REJECTED: status_icon = "❌"
                    
                    campaign_msg += f"{status_icon} *{p.campaign.name}*\n"
                    campaign_msg += f"Status: {p.status.value}\n"
                    campaign_msg += f"🔗 [Review Briefing]({base_url}/{p.campaign_id}?vol_id={volunteer.id})\n\n"
                
                await send_and_log(bg=background_tasks, chat_id=chat_id, text=campaign_msg)
            return {"status": "campaigns_sent"}

        if text == "/cancel":
            # Identify volunteer
            stmt_v = select(Volunteer).where(Volunteer.telegram_chat_id == chat_id)
            volunteer = (await db.execute(stmt_v)).scalar_one_or_none()
            
            if not volunteer:
                await send_and_log(bg=background_tasks, chat_id=chat_id, text="⚠️ *Error*: You are not a registered volunteer.")
                return {"status": "unregistered"}

            # Fetch most recent active dispatch
            stmt_m = (
                select(MarketplaceDispatch)
                .join(MarketplaceNeed, MarketplaceDispatch.marketplace_need_id == MarketplaceNeed.id)
                .where(MarketplaceDispatch.volunteer_id == volunteer.id, MarketplaceDispatch.status == DispatchStatus.ACCEPTED)
                .order_by(MarketplaceDispatch.created_at.desc())
                .limit(1)
            )
            active = (await db.execute(stmt_m)).scalar_one_or_none()
            
            if not active:
                await send_and_log(bg=background_tasks, chat_id=chat_id, text="ℹ️ *No active missions to cancel.*")
            else:
                # Cancel the mission
                active.status = DispatchStatus.FAILED
                
                # Re-open the need
                stmt_n = select(MarketplaceNeed).where(MarketplaceNeed.id == active.marketplace_need_id)
                need = (await db.execute(stmt_n)).scalar_one()
                need.status = NeedStatus.OPEN
                
                # 🟢 STATUS SYNC: Revert volunteer to AVAILABLE
                volunteer.status = VolunteerStatus.AVAILABLE
                
                await db.commit()
                await send_and_log(bg=background_tasks, chat_id=chat_id, text="⚠️ *Mission Cancelled.* The request has been returned to the open pool. We hope you can join us again soon! 🤝")
            return {"status": "mission_cancelled"}
            

        # --- 3. Handle OTP Verification (Donor-Side Completion) ---
        if text and text.isdigit() and len(text) == 6:
            try:
                # Check if this user has an active donor mission
                # CRITICAL: Only check for ACCEPTED missions (SENT missions don't have OTPs generated yet)
                stmt_otp = (
                    select(MarketplaceDispatch)
                    .join(MarketplaceNeed, MarketplaceDispatch.marketplace_need_id == MarketplaceNeed.id)
                    .join(MarketplaceAlert, MarketplaceNeed.marketplace_alert_id == MarketplaceAlert.id)
                    .where(
                        MarketplaceAlert.chat_id == chat_id,
                        MarketplaceDispatch.status == DispatchStatus.ACCEPTED
                    )
                    .order_by(desc(MarketplaceDispatch.created_at))
                    .limit(1)
                )
                dispatch = (await db.execute(stmt_otp)).scalar_one_or_none()
                
                if dispatch:
                    print(f"[TRACE] OTP Detected from Donor. Dispatch ID: {dispatch.id}")
                    
                    # 1. Check Expiry
                    if dispatch.otp_expires_at:
                        # Ensure timezone-aware comparison
                        now = datetime.now(timezone.utc)
                        expiry = dispatch.otp_expires_at
                        # SQLAlchemy might return it as naive; ensure it's treated as UTC aware
                        if expiry.tzinfo is None:
                            expiry = expiry.replace(tzinfo=timezone.utc)
                        
                        if now > expiry:
                            print(f"[DEBUG] OTP EXPIRED: Now={now}, Expiry={expiry}, Diff={now - expiry}")
                            await send_and_log(bg=background_tasks, chat_id=chat_id, text="⚠️ *OTP Expired*: This code is no longer valid. Please ask the volunteer to re-accept the mission or contact support.")
                            return {"status": "otp_expired"}

                    # 2. Verify Code
                    if verify_otp(text, dispatch.otp_hash):
                        # SUCCESS: Complete the Mission
                        dispatch.status = DispatchStatus.COMPLETED
                        dispatch.otp_used = True
                        
                        # Update related need
                        stmt_need = select(MarketplaceNeed).where(MarketplaceNeed.id == dispatch.marketplace_need_id).options(selectinload(MarketplaceNeed.marketplace_alert))
                        need = (await db.execute(stmt_need)).scalar_one()
                        need.status = NeedStatus.COMPLETED
                        
                        # Recovered Item to Inventory
                                                
                        item_name = f"Recovered {need.type.name}"
                        if need.marketplace_alert and need.marketplace_alert.item and need.marketplace_alert.item != "N/A":
                            item_name = need.marketplace_alert.item

                        recovery_entry = MarketplaceInventory(
                            org_id=need.org_id,
                            item_name=item_name,
                            quantity=1.0, 
                            unit=need.quantity,
                            collected_at=datetime.now(timezone.utc)
                        )
                        db.add(recovery_entry)
                        
                        # Update Volunteer Stats
                        stmt_stats = select(VolunteerStats).where(VolunteerStats.volunteer_id == dispatch.volunteer_id)
                        stats = (await db.execute(stmt_stats)).scalar_one_or_none()
                        if stats: stats.completions += 1
                        
                        # 🟢 STATUS SYNC: Revert volunteer to AVAILABLE
                        stmt_v_reset = select(Volunteer).where(Volunteer.id == dispatch.volunteer_id)
                        v_reset = (await db.execute(stmt_v_reset)).scalar_one()
                        v_reset.status = VolunteerStatus.AVAILABLE
                        
                        await db.commit()
                        print(f"[TRACE] Mission {dispatch.id} COMPLETED via Donor OTP.")
                        
                        # --- Notification Center: Mission Completed ---
                        await notification_service.notify_mission_completed(
                            db=db,
                            org_id=need.org_id,
                            mission_name=need.type.name
                        )
                        
                        # Feedback to Donor
                        impact_msg = (
                            "🎊 *IMPACT RECORDED!* 🎊\n\n"
                            "Thank you so much! Your contribution has been safely collected and logged. "
                            "Because of you, we are one step closer to a hunger-free world. 🌍🤝"
                        )
                        await send_and_log(bg=background_tasks, chat_id=chat_id, text=impact_msg)
                        
                        # Feedback to Volunteer
                        stmt_vol = select(Volunteer).where(Volunteer.id == dispatch.volunteer_id)
                        volunteer = (await db.execute(stmt_vol)).scalar_one()
                        if volunteer.telegram_chat_id:
                            await telegram_service.send_message(
                                chat_id=volunteer.telegram_chat_id,
                                text="✅ *Mission Complete!* The donor has verified your pickup. Great job, Hero! 🌟"
                            )
                        return {"status": "otp_verified"}
                    else:
                        await send_and_log(bg=background_tasks, chat_id=chat_id, text="⚠️ *Invalid Code.* Please check the 6-digit code shown by the volunteer.")
                        return {"status": "otp_invalid"}
                else:
                    # User typed a 6-digit number but we didn't find an active mission for them as donor
                    print(f"[TRACE] 6-digit number received from {chat_id} but no active ACCEPTED dispatch found for this donor.")
                    await send_and_log(bg=background_tasks, chat_id=chat_id, text="🔍 *Mission Not Found*: We found no active missions linked to your account for this PIN. If you are a volunteer, please ask the donor to type this code in their chat! 🤝")
                    return {"status": "no_active_mission"}
            except Exception as e:
                print(f"[ERROR] OTP Verification Webhook Failed: {e}")
                traceback.print_exc()
                await send_and_log(bg=background_tasks, chat_id=chat_id, text="⚠️ *System Error*: Something went wrong while verifying your code. Please try again in a few moments.")
                return {"status": "error"}

        # --- 4. Surplus Reporting (The AI Ingestion Flow) ---
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

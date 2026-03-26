from fastapi import APIRouter, Depends, Request
import traceback
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload
from backend.app.database import get_db
from backend.app.models import Volunteer, Dispatch, DispatchStatus, SurplusAlert, Organization, Need, VolunteerStats
from backend.app.services.otp import generate_otp_pair
from backend.app.services.telegram_service import telegram_service
import os

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
                    
                    # --- Notify Donor if applicable ---
                    stmt_need = select(Need).where(Need.id == dispatch.need_id)
                    need = (await db.execute(stmt_need)).scalar_one_or_none()
                    if need and need.surplus_alert_id:
                        stmt_alert = select(SurplusAlert).where(SurplusAlert.id == need.surplus_alert_id)
                        alert = (await db.execute(stmt_alert)).scalar_one_or_none()
                        if alert:
                            donor_msg = (
                                f"🚚 *Volunteer On The Way!*\n\n"
                                f"Volunteer *{volunteer.name}* has accepted your donation pickup.\n"
                                f"Please ask them for their *6-digit verification code* and reply here with:\n\n"
                                f"`CONFIRM <CODE>` (e.g., `CONFIRM 123456`)"
                            )
                            await telegram_service.send_message(chat_id=alert.chat_id, text=donor_msg)
            
            # --- Role Selection Callbacks ---
            if data_payload == "join_volunteer":
                # Show the share contact button
                kb = {
                    "keyboard": [[{"text": "📱 Share Contact to Verify", "request_contact": True}]],
                    "one_time_keyboard": True,
                    "resize_keyboard": True
                }
                await telegram_service.send_message(
                    chat_id=chat_id,
                    text="Great! To link your volunteer account, please click the button below to share your contact details with us.",
                    reply_markup=kb
                )
                
            if data_payload == "donate_surplus":
                # Check if we already have this donor's contact
                stmt = select(SurplusAlert).where(SurplusAlert.chat_id == chat_id, SurplusAlert.phone_number != None)
                existing_alert = (await db.execute(stmt)).first()
                
                if existing_alert:
                    instr = (
                        "📦 *Great! Reporting Surplus Items*\n\n"
                        "To help local NGOs coordinate better, please send your donation details in this format:\n\n"
                        "`[ITEM] [QUANTITY] [LOCATION] [ANY NOTES]`\n\n"
                        "*Example*: `Rice 50kg Sector 15 Near Park.`"
                    )
                    await telegram_service.send_message(chat_id=chat_id, text=instr)
                else:
                    # Trigger donation flow instructions
                    await telegram_service.send_message(
                        chat_id=chat_id,
                        text="🎁 *Donation Portal*\n\nTo report surplus, please share your contact first so NGOs can coordinate the pickup with you.",
                        reply_markup={
                            "keyboard": [[{"text": "📱 Share Donor Contact", "request_contact": True}]],
                            "one_time_keyboard": True,
                            "resize_keyboard": True
                        }
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
                # Ensure menu is synced for the volunteer
                await telegram_service.set_bot_commands(chat_id=chat_id)
                await telegram_service.send_message(
                    chat_id=chat_id,
                    text=f"Welcome back, *{volunteer.name}*! You are active and ready for missions. 🚀"
                )
            else:
                first_name = message.get("from", {}).get("first_name", "there")
                welcome_caption = (
                    f"Hey 👋 *{first_name}*!\n\n"
                    f"🤝 *WELCOME TO SAHYOG SETU*\n\n"
                    f"The ultimate bridge connecting your kindness (Surplus Food) to those who need it most.\n\n"
                    f"How would you like to contribute today?\n"
                    f"👇 *Select your role below*:"
                )
                
                inline_kb = {
                    "inline_keyboard": [
                        [{"text": "🙋‍♂️ Join as Volunteer", "callback_data": "join_volunteer"}],
                        [{"text": "🎁 Donate Surplus Food", "callback_data": "donate_surplus"}]
                    ]
                }
                
                # Check for local poster
                import os
                poster_path = "backend/app/static/welcome.png"
                if not os.path.exists(poster_path):
                    # Fallback to text if image missing
                    await telegram_service.send_message(
                        chat_id=chat_id,
                        text=welcome_caption,
                        reply_markup=inline_kb
                    )
                else:
                    await telegram_service.send_photo(
                        chat_id=chat_id,
                        photo_path=poster_path,
                        caption=welcome_caption,
                        reply_markup=inline_kb
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

        if text == "/leaderboard":
            # Fetch top 5 volunteers by completions
            stmt = select(Volunteer).where(Volunteer.telegram_chat_id == chat_id)
            volunteer = (await db.execute(stmt)).scalar_one_or_none()
            if not volunteer or not volunteer.telegram_active:
                await telegram_service.send_message(chat_id=chat_id, text="🔒 This command is for verified volunteers only.")
                return {"status": "unauthorized"}

            stmt = (
                select(Volunteer, VolunteerStats)
                .join(VolunteerStats, Volunteer.id == VolunteerStats.volunteer_id)
                .order_by(desc(VolunteerStats.completions))
                .limit(5)
            )
            results = (await db.execute(stmt)).all()
            
            if results:
                leaderboard_text = "🏆 *Volunteer Leaderboard*\n\n"
                for i, (vol, stats) in enumerate(results, 1):
                    medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🎖"
                    leaderboard_text += f"{medal} *{vol.name}*: `{stats.completions}` completions\n"
                await telegram_service.send_message(chat_id=chat_id, text=leaderboard_text)
            else:
                await telegram_service.send_message(chat_id=chat_id, text="🏆 Leaderboard is empty. Be the first to complete a mission!")
            return {"status": "leaderboard_sent"}

        if text == "/my_missions" or text == "/status":
            stmt = (
                select(Volunteer)
                .where(Volunteer.telegram_chat_id == chat_id)
                .options(selectinload(Volunteer.stats))
            )
            volunteer = (await db.execute(stmt)).scalar_one_or_none()
            
            if volunteer and volunteer.telegram_active:
                stats = volunteer.stats
                status_report = (
                    f"👤 *Volunteer Profile*\n"
                    f"Name: {volunteer.name}\n"
                    f"Trust Tier: `{volunteer.trust_tier.name}`\n"
                    f"Completions: `{stats.completions if stats else 0}`\n"
                    f"No-Shows: `{stats.no_shows if stats else 0}`\n\n"
                    f"Status: *Active*"
                )
                await telegram_service.send_message(chat_id=chat_id, text=status_report)
            else:
                await telegram_service.send_message(chat_id=chat_id, text="🔒 This profile is for verified volunteers only. Please link your account first.")
            return {"status": "status_sent"}

        if text == "/about":
            about_text = (
                "ℹ️ *About Sahyog Setu*\n\n"
                "Sahyog Setu is an AI-powered logistics bridge connecting surplus food from donors to NGOs in real-time.\n\n"
                "🌍 *Mission*: Zero Hunger through efficient distribution.\n"
                "🤝 *Partners*: Helping local NGOs scale their impact with secure tracking and volunteer coordination."
            )
            await telegram_service.send_message(chat_id=chat_id, text=about_text)
            return {"status": "about_sent"}

        if text == "/tutorial":
            tutorial_text = (
                "📖 *How to use Sahyog Setu*\n\n"
                "1️⃣ **For Volunteers**: Register via `/start`, click 'I am a Volunteer', and share your contact. You'll receive mission alerts. Click 'Accept', get the OTP, and provide it at the pickup point.\n\n"
                "2️⃣ **For Donors**: Click '🎁 Donate Surplus', follow the instructions to report items. Wait for notification when a volunteer is nearby, and verify them using `CONFIRM <CODE>`."
            )
            await telegram_service.send_message(chat_id=chat_id, text=tutorial_text)
            return {"status": "tutorial_sent"}

        if text == "/cancel":
            # Identify Volunteer
            stmt = select(Volunteer).where(Volunteer.telegram_chat_id == chat_id)
            volunteer = (await db.execute(stmt)).scalar_one_or_none()
            if not volunteer or not volunteer.telegram_active:
                await telegram_service.send_message(chat_id=chat_id, text="🔒 This command is for verified volunteers only.")
                return {"status": "unauthorized"}

            # Cancel the latest active dispatch for this volunteer
            stmt = (
                select(Dispatch)
                .join(Volunteer, Dispatch.volunteer_id == Volunteer.id)
                .where(Volunteer.telegram_chat_id == chat_id, Dispatch.status == DispatchStatus.SENT)
                .order_by(desc(Dispatch.created_at))
            )
            dispatch = (await db.execute(stmt)).scalar_one_or_none()
            if dispatch:
                dispatch.status = DispatchStatus.FAILED
                await db.commit()
                await telegram_service.send_message(chat_id=chat_id, text="⚠️ *Mission Cancelled*. Please avoid cancellations as they affect your Trust Tier.")
            else:
                await telegram_service.send_message(chat_id=chat_id, text="❌ No active missions found to cancel.")
            return {"status": "cancel_handled"}

        if text == "/donate" or text == "🎁 Donate Surplus":
            # Check if we already have this donor's contact
            stmt = select(SurplusAlert).where(SurplusAlert.chat_id == chat_id, SurplusAlert.phone_number != None)
            existing_alert = (await db.execute(stmt)).first()
            
            if existing_alert:
                instr = (
                    "📦 *Great! Reporting Surplus Items*\n\n"
                    "To help local NGOs coordinate better, please send your donation details in this format:\n\n"
                    "`[ITEM] [QUANTITY] [LOCATION] [ANY NOTES]`\n\n"
                    "*Example*: `Rice 50kg Sector 15 Near Park. Ready for pickup till 8 PM.`"
                )
                await telegram_service.send_message(chat_id=chat_id, text=instr)
            else:
                donor_keyboard = {
                    "keyboard": [[{"text": "📱 Share Contact for NGOs", "request_contact": True}]],
                    "one_time_keyboard": True,
                    "resize_keyboard": True
                }
                await telegram_service.send_message(
                    chat_id=chat_id,
                    text="To report surplus, please share your contact first so NGOs can coordinate the pickup with you.",
                    reply_markup=donor_keyboard
                )
            return {"status": "donor_onboarding_started"}

        # --- 2.6 Handle Donor CONFIRM command ---
        if text.upper().startswith("CONFIRM"):
            parts = text.split()
            if len(parts) > 1:
                otp_code = parts[1].strip()
                # Find the dispatch linked to this donor's alert
                stmt = (
                    select(Dispatch)
                    .join(Need, Dispatch.need_id == Need.id)
                    .join(SurplusAlert, Need.surplus_alert_id == SurplusAlert.id)
                    .where(SurplusAlert.chat_id == chat_id, Dispatch.otp_used == False)
                    .order_by(Dispatch.created_at.desc())
                )
                from backend.app.services.otp import verify_otp
                result = await db.execute(stmt)
                dispatch = result.scalar_one_or_none()
                
                if dispatch:
                    if verify_otp(otp_code, dispatch.otp_hash):
                        dispatch.otp_used = True
                        dispatch.status = DispatchStatus.CONFIRMED
                        
                        need_stmt = select(Need).where(Need.id == dispatch.need_id)
                        need = (await db.execute(need_stmt)).scalar_one()
                        from backend.app.models import NeedStatus
                        need.status = NeedStatus.COMPLETED
                        
                        await db.commit()
                        await telegram_service.send_message(
                            chat_id=chat_id,
                            text="✅ *Mission Complete!* Thank you for your donation. Your impact has been recorded. 🙏"
                        )
                        return {"status": "donor_verified"}
                    else:
                        await telegram_service.send_message(
                            chat_id=chat_id,
                            text="❌ *Invalid Code*. Please check the code provided by the volunteer."
                        )
                        return {"status": "donor_verify_failed"}
                else:
                    await telegram_service.send_message(
                        chat_id=chat_id,
                        text="❌ *No active mission* found for your donation alerts."
                    )
                    return {"status": "no_active_mission"}

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
                    # Trigger menu sync for volunteer
                    await telegram_service.set_bot_commands(chat_id=chat_id)
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
                # Trigger menu sync for volunteer
                await telegram_service.set_bot_commands(chat_id=chat_id)
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
                # This could be a DONOR sharing contact
                # Check if they recently clicked "Donate Surplus" or just share contact
                # We'll save it as a placeholder SurplusAlert or just confirmation
                donor_name = contact.get("first_name", "Donor")
                
                # Save as a pending alert (without body yet)
                alert = SurplusAlert(
                    chat_id=chat_id,
                    phone_number=phone,
                    donor_name=donor_name,
                    message_body="[Pending Report]"
                )
                db.add(alert)
                await db.commit()
                
                instr = (
                    "✅ *Contact Verified!*\n\n"
                    "Now, please send your donation details in this format:\n\n"
                    "`[ITEM] [QUANTITY] [LOCATION] [ANY NOTES]`\n\n"
                    "*Example*: `Rice 50kg Sector 15 Near Park. Ready for pickup till 8 PM.`"
                )
                await telegram_service.send_message(chat_id=chat_id, text=instr)
                return {"status": "donor_contact_saved"}

        # --- 4. Fallback: Donor Flow ---
        # Identification logic
        stmt = select(Volunteer).where(Volunteer.telegram_chat_id == chat_id)
        volunteer = (await db.execute(stmt)).scalar_one_or_none()
        
        if not volunteer:
            # Check for a pending alert (one created when contact was shared)
            stmt = (
                select(SurplusAlert)
                .where(SurplusAlert.chat_id == chat_id, SurplusAlert.message_body == "[Pending Report]")
                .order_by(desc(SurplusAlert.created_at))
            )
            pending_alert = (await db.execute(stmt)).scalar_one_or_none()
            
            if pending_alert:
                pending_alert.message_body = text
                await db.commit()
            else:
                # Save as new Surplus Alert
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

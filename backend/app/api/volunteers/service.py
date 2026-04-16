from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from backend.app.models import Volunteer, VolunteerStats, User, UserRole
from backend.app.services.auth_utils import get_password_hash
import random
import string
from typing import Optional
from .schemas import VolunteerProfileResponse, VolunteerResponse

async def get_my_volunteer(db: AsyncSession, user_id: int) -> Volunteer:
    """Helper to fetch a volunteer profile linked to a User ID."""
    stmt = (
        select(Volunteer)
        .options(selectinload(Volunteer.stats))
        .where(Volunteer.user_id == user_id)
    )
    res = await db.execute(stmt)
    volunteer = res.scalar_one_or_none()
    if not volunteer:
        raise HTTPException(status_code=404, detail="Volunteer profile not found")
    return volunteer

async def onboard_volunteer_via_telegram(db: AsyncSession, norm_phone: str, chat_id: str):
    """
    Business Logic: Activates a volunteer via Telegram contact sharing.
    - Idempotent: Handles both new account creation and linking existing ones.
    - Generates unique username/password for new users.
    - Returns credentials or account status.
    """
    # 1. Match Phone
    stmt = select(Volunteer).where(Volunteer.phone_number.like(f"%{norm_phone}"))
    v = (await db.execute(stmt)).scalar_one_or_none()
    
    if not v:
        return None # No match found
        
    # 2. Handle Case: Existing User already linked to this Volunteer
    if v.user_id:
        user = await db.get(User, v.user_id)
        
        # Link/Update Telegram details
        v.telegram_chat_id = chat_id
        v.telegram_active = True
        
        await db.commit()
        return {
            "name": v.name, 
            "username": user.username if user else "your-web-account", 
            "already_active": True
        }

    # 3. Logic: Generate Unique Username (firstname + last_4_digits)
    first_name = v.name.split()[0].lower()
    clean_phone = norm_phone[-4:]
    base_username = f"{first_name}{clean_phone}"
    
    username = base_username
    # Simple collision guard
    for i in range(5):
        u_check = select(User).where(User.username == username)
        if not (await db.execute(u_check)).scalar_one_or_none():
            break
        username = f"{base_username}{random.randint(10, 99)}"

    # 4. Logic: Generate Random Password (firstname + @ + 4 digits)
    random_digits = "".join(random.choices(string.digits, k=4))
    raw_password = f"{first_name}@{random_digits}"
    
    # 5. Create User Record
    new_user = User(
        org_id=v.org_id,
        username=username,
        hashed_password=get_password_hash(raw_password),
        full_name=v.name,
        role=UserRole.VOLUNTEER,
        is_active=True
    )
    db.add(new_user)
    await db.flush()
    v.user_id = new_user.id
        
    # 6. Activate Telegram Status
    v.telegram_chat_id = chat_id
    v.telegram_active = True
    
    # 7. Ensure stats record exists
    stmt_stats = select(VolunteerStats).where(VolunteerStats.volunteer_id == v.id)
    if not (await db.execute(stmt_stats)).scalar_one_or_none():
        db.add(VolunteerStats(volunteer_id=v.id))
        
    await db.commit()
    return {
        "name": v.name, 
        "username": username, 
        "password": raw_password,
        "already_active": False
    }

async def increment_volunteer_completions(db: AsyncSession, volunteer_id: int):
    """
    Helper to standardise stats updates across dispatches and webhooks.
    Includes automated trust_tier upgrade on first successful mission.
    """
    stmt = select(VolunteerStats).where(VolunteerStats.volunteer_id == volunteer_id)
    stats = (await db.execute(stmt)).scalar_one_or_none()
    
    if stats:
        stats.completions += 1
        
        # Auto-upgrade to FIELD_VERIFIED on first completion
        v_stmt = select(Volunteer).where(Volunteer.id == volunteer_id)
        v = (await db.execute(v_stmt)).scalar_one_or_none()
        if v and v.trust_tier != "FIELD_VERIFIED":
            # Only upgrade if they were UNVERIFIED or ID_VERIFIED
            v.trust_tier = "FIELD_VERIFIED"
            
        await db.flush()

def build_volunteer_response(
    v: Volunteer, 
    comp: int = 0, 
    noshow: int = 0, 
    hours: float = 0.0, 
    img_url: Optional[str] = None
) -> VolunteerResponse:
    """Consolidated logic to build the volunteer response for NGO views."""
    resp = VolunteerResponse.model_validate(v)
    resp.completions = comp or 0
    resp.no_shows = noshow or 0
    resp.hours_served = hours or 0.0
    resp.profile_image_url = img_url
    return resp
            
def build_profile_response(v: Volunteer, user: User) -> VolunteerProfileResponse:
    """Consolidated logic to build the volunteer profile response schema."""
    return VolunteerProfileResponse(
        id=v.id,
        name=v.name,
        phone_number=v.phone_number,
        email=user.email,
        is_active=v.telegram_active,
        is_email_verified=user.is_email_verified,
        trust_tier=v.trust_tier,
        trust_score=v.trust_score,
        id_verified=v.id_verified,
        aadhaar_last_4=v.aadhaar_last_4,
        skills=v.skills,
        zone=v.zone,
        completions=v.stats.completions if v.stats else 0,
        hours_served=v.stats.hours_served if v.stats else 0.0,
        profile_image_url=user.profile_image_url,
        status=v.status
    )

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from backend.app.models import Volunteer, VolunteerStats, User, UserRole
from backend.app.services.auth_utils import get_password_hash
import random
import string

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
    - Generates username/password.
    - Creates User record.
    - Activates Volunteer record.
    """
    # 1. Match Phone
    stmt = select(Volunteer).where(Volunteer.phone_number.like(f"%{norm_phone}"))
    v = (await db.execute(stmt)).scalar_one_or_none()
    
    if not v:
        return None # No match found
        
    # 2. Logic: first_name + last_4_digits of number
    first_name = v.name.split()[0].lower()
    clean_phone = norm_phone[-4:]
    username = f"{first_name}{clean_phone}"
    
    # 3. Logic: firstname + @ + random 3 numbers
    random_digits = "".join(random.choices(string.digits, k=3))
    raw_password = f"{first_name}@{random_digits}"
    
    # 4. Idempotent User Creation
    if not v.user_id:
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
        
    # 5. Activate
    v.telegram_chat_id = chat_id
    v.telegram_active = True
    
    # Ensure stats initialized
    stmt_stats = select(VolunteerStats).where(VolunteerStats.volunteer_id == v.id)
    if not (await db.execute(stmt_stats)).scalar_one_or_none():
        db.add(VolunteerStats(volunteer_id=v.id))
        
    await db.commit()
    return {"name": v.name, "username": username, "password": raw_password}

async def increment_volunteer_completions(db: AsyncSession, volunteer_id: int):
    """
    Helper to standardise stats updates across dispatches and webhooks.
    """
    stmt = select(VolunteerStats).where(VolunteerStats.volunteer_id == volunteer_id)
    stats = (await db.execute(stmt)).scalar_one_or_none()
    if stats:
        stats.completions += 1

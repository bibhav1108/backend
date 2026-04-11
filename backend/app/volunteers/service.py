from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from backend.app.models import Volunteer, VolunteerStats

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

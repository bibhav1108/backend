from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, desc
from backend.app.database import get_db
from backend.app.models import Notification, User
from backend.app.api.deps import get_current_user
from backend.app.notifications.schemas import NotificationResponse
from typing import List

router = APIRouter()

@router.get("/", response_model=List[NotificationResponse])
async def list_notifications(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Fetch the latest 50 notifications for the current NGO dashboard.
    Shows både system-wide alerts and NGO-specific events.
    """
    stmt = (
        select(Notification)
        .where(
            (Notification.org_id == current_user.org_id) | (Notification.org_id == None)
        )
        .order_by(desc(Notification.created_at))
        .limit(50)
    )
    result = await db.execute(stmt)
    return result.scalars().all()

@router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Marks a specific notification as read."""
    stmt = select(Notification).where(
        Notification.id == notification_id,
        Notification.org_id == current_user.org_id
    )
    notif = (await db.execute(stmt)).scalar_one_or_none()
    
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    notif.is_read = True
    await db.commit()
    return {"status": "success"}

@router.post("/mark-all-read")
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Marks all unread notifications for the NGO as read."""
    stmt = (
        update(Notification)
        .where(Notification.org_id == current_user.org_id, Notification.is_read == False)
        .values(is_read=True)
    )
    await db.execute(stmt)
    await db.commit()
    return {"status": "success", "message": "All notifications marked as read"}

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from backend.app.models import Notification, NotificationType, Organization
from typing import Optional, Dict, Any, List

class NotificationService:
    async def create_notification(
        self,
        db: AsyncSession,
        org_id: Optional[int],
        notification_type: NotificationType,
        title: str,
        message: str,
        priority: str = "INFO",
        data: Optional[Dict[str, Any]] = None
    ):
        """
        Centrally creates a notification record in the database.
        These are intended for the NGO coordinator dashboard alerts.
        """
        notification = Notification(
            org_id=org_id,
            type=notification_type,
            title=title,
            message=message,
            priority=priority,
            data=data
        )
        db.add(notification)
        # We don't commit here; we assume the caller will commit the session
        return notification

    # --- Helper methods for specific event types ---
    
    async def notify_donor_alert(self, db: AsyncSession, alert_id: int, item: str, location: str):
        """
        Multi-casts the donor alert to all ACTIVE NGOs.
        Each NGO gets its own notification instance to track its own 'read' status.
        """
        # Fetch all active NGOs
        stmt = select(Organization).where(Organization.status == "active")
        result = await db.execute(stmt)
        active_orgs = result.scalars().all()
        
        notifications = []
        for org in active_orgs:
            notif = await self.create_notification(
                db=db,
                org_id=org.id,
                notification_type=NotificationType.DONOR_ALERT,
                title="🎁 New Donation Alert",
                message=f"Someone reported surplus {item} at {location}. Ready for review!",
                priority="INFO",
                data={"alert_id": alert_id}
            )
            notifications.append(notif)
        
        return notifications

    async def cleanup_alert_notifications(self, db: AsyncSession, alert_id: int, claiming_org_id: Optional[int] = None):
        """
        Removes all notifications related to a specific alert for all NGOs
        EXCEPT the one that claimed it (or everyone if claiming_org_id is None).
        
        This keeps the tables clean and ensures stale alerts 'go away'.
        """
        # SQL check for JSON field: data->'alert_id' == alert_id
        # PostgreSQL syntax via SQLAlchemy text or JSON column support
        stmt = delete(Notification).where(
            Notification.type == NotificationType.DONOR_ALERT,
            Notification.data["alert_id"].as_integer() == alert_id
        )
        
        if claiming_org_id:
            stmt = stmt.where(Notification.org_id != claiming_org_id)
            
        await db.execute(stmt)
        # Caller handles commit

    async def notify_mission_accepted(self, db: AsyncSession, org_id: int, volunteer_name: str, mission_name: str, dispatch_id: int):
        return await self.create_notification(
            db=db,
            org_id=org_id,
            notification_type=NotificationType.MISSION_ACCEPTED,
            title="🦸 Hero on the Way",
            message=f"Volunteer {volunteer_name} accepted the mission: {mission_name}.",
            priority="SUCCESS",
            data={"dispatch_id": dispatch_id, "mission_name": mission_name}
        )

    async def notify_mission_completed(self, db: AsyncSession, org_id: int, mission_name: str):
        return await self.create_notification(
            db=db,
            org_id=org_id,
            notification_type=NotificationType.MISSION_COMPLETED,
            title="✅ Mission Successful",
            message=f"Success! The mission '{mission_name}' has been completed and items verified.",
            priority="SUCCESS",
            data={"mission_name": mission_name}
        )

    async def notify_campaign_interest(self, db: AsyncSession, org_id: int, volunteer_name: str, campaign_name: str, campaign_id: int):
        return await self.create_notification(
            db=db,
            org_id=org_id,
            notification_type=NotificationType.CAMPAIGN_INTEREST,
            title="📢 New Campaign Interest",
            message=f"Volunteer {volunteer_name} expressed interest in joining '{campaign_name}'.",
            priority="INFO",
            data={"campaign_id": campaign_id, "volunteer_name": volunteer_name}
        )

notification_service = NotificationService()

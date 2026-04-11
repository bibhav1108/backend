from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Dict, Any
from backend.app.models import NotificationType

class NotificationBase(BaseModel):
    type: NotificationType
    title: str
    message: str
    priority: str = "INFO"
    data: Optional[Dict[str, Any]] = None

class NotificationCreate(NotificationBase):
    org_id: Optional[int] = None

class NotificationResponse(NotificationBase):
    id: int
    org_id: Optional[int]
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True

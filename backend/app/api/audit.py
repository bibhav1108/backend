from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from backend.app.database import get_db
from backend.app.models import AuditTrail, User
from backend.app.api.deps import get_current_user
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()

class AuditResponse(BaseModel):
    id: int
    event_type: str
    target_id: str | None
    notes: str | None
    created_at: datetime

    class Config:
        from_attributes = True

class PaginatedAuditResponse(BaseModel):
    total_count: int
    items: List[AuditResponse]

@router.get("/", response_model=PaginatedAuditResponse)
async def list_audit_logs(
    skip: int = 0,
    limit: int = 20,
    event_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Fetch activity logs for the current NGO with pagination and filtering."""
    
    # Base query
    base_stmt = select(AuditTrail).where(AuditTrail.org_id == current_user.org_id)
    
    # Apply filter
    if event_type:
        base_stmt = base_stmt.where(AuditTrail.event_type == event_type)
    
    # 1. Get total count
    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total_count = (await db.execute(count_stmt)).scalar_one()

    # 2. Get items
    query_stmt = (
        base_stmt
        .order_by(AuditTrail.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query_stmt)
    items = result.scalars().all()

    return {
        "total_count": total_count,
        "items": items
    }

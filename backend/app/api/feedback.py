from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.database import get_db
from backend.app.models import PlatformFeedback, FeedbackType, User, UserRole
from backend.app.api.deps import get_current_user
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

router = APIRouter()

# --- Schemas ---

class FeedbackCreate(BaseModel):
    type: FeedbackType
    rating: Optional[float] = None
    category: Optional[str] = None
    content: str

class FeedbackRead(BaseModel):
    id: int
    user_id: int
    user_name: str
    user_role: str
    type: FeedbackType
    rating: Optional[float]
    category: Optional[str]
    content: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

# --- Middleware-like Dependency ---
async def require_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != UserRole.SYSTEM_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have administrative privileges."
        )
    return current_user

# --- Endpoints ---

@router.post("/submit", status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    feedback_in: FeedbackCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Authenticated users (NGOs, Volunteers) submit platform reviews or issue requests.
    """
    new_feedback = PlatformFeedback(
        user_id=current_user.id,
        type=feedback_in.type,
        rating=feedback_in.rating,
        category=feedback_in.category,
        content=feedback_in.content
    )
    db.add(new_feedback)
    await db.commit()
    await db.refresh(new_feedback)
    
    return {"message": "Thank you! Your feedback has been sent to the admin team.", "id": new_feedback.id}

@router.get("/list", response_model=List[FeedbackRead])
async def list_feedback(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """
    System Admins view all community feedback and issues.
    """
    stmt = (
        select(PlatformFeedback, User.full_name, User.role)
        .join(User, PlatformFeedback.user_id == User.id)
        .order_by(PlatformFeedback.created_at.desc())
    )
    result = await db.execute(stmt)
    
    feedback_list = []
    for row in result:
        fb, name, role = row
        feedback_list.append(
            FeedbackRead(
                id=fb.id,
                user_id=fb.user_id,
                user_name=name or "Anonymous",
                user_role=role.value,
                type=fb.type,
                rating=fb.rating,
                category=fb.category,
                content=fb.content,
                status=fb.status,
                created_at=fb.created_at
            )
        )
    
    return feedback_list

@router.patch("/{fb_id}/status")
async def update_feedback_status(
    fb_id: int,
    status_val: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """
    System Admins mark issues as RESOLVED.
    """
    stmt = select(PlatformFeedback).where(PlatformFeedback.id == fb_id)
    fb = (await db.execute(stmt)).scalar_one_or_none()
    
    if not fb:
        raise HTTPException(status_code=404, detail="Feedback record not found")
        
    fb.status = status_val
    await db.commit()
    
    return {"message": f"Feedback status updated to {status_val}"}

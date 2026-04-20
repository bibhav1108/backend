from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
import os
import shutil
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.database import get_db
from backend.app.models import User, NGO_Campaign, Inventory, Volunteer
from backend.app.api.deps import get_current_user
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime
from backend.app.services import cloudinary_service
from backend.app.services.auth_utils import get_password_hash, verify_password

router = APIRouter()

# --- Schemas ---

class UserRead(BaseModel):
    id: int
    org_id: Optional[int]
    email: EmailStr
    full_name: Optional[str]
    role: str
    is_active: bool
    created_at: datetime
    trust_tier: Optional[str] = None
    telegram_active: Optional[bool] = None
    profile_image_url: Optional[str] = None

    class Config:
        from_attributes = True

class UserStats(BaseModel):
    total_campaigns: int
    total_inventory: int
    total_volunteers: int

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None

class PasswordChange(BaseModel):
    old_password: str
    new_password: str

# --- Endpoints ---

@router.get("/me", response_model=UserRead)
async def get_my_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve the profile of the currently logged-in user, including volunteer status if applicable.
    """
    from backend.app.models import Volunteer
    
    stmt = select(Volunteer).where(Volunteer.user_id == current_user.id)
    volunteer = (await db.execute(stmt)).scalar_one_or_none()
    
    # We create a dictionary to merge the user data with volunteer data
    user_data = {
        "id": current_user.id,
        "org_id": current_user.org_id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role,
        "is_active": current_user.is_active,
        "created_at": current_user.created_at,
        "profile_image_url": current_user.profile_image_url,
        "trust_tier": volunteer.trust_tier if volunteer else None,
        "telegram_active": volunteer.telegram_active if volunteer else None
    }
    
    return user_data

@router.get("/", response_model=List[UserRead])
async def list_org_users(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List all users within the same organization as the current user.
    Enforces Data Isolation.
    """
    stmt = select(User).where(User.org_id == current_user.org_id)
    result = await db.execute(stmt)
    users = result.scalars().all()
    return users

@router.get("/me/stats", response_model=UserStats)
async def get_my_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get real-time metrics for the coordinator's organization.
    """
    if not current_user.org_id:
        return {
            "total_campaigns": 0,
            "total_inventory": 0,
            "total_volunteers": 0
        }
        
    from sqlalchemy import func
    
    # 1. Count Campaigns
    campaign_stmt = select(func.count(NGO_Campaign.id)).where(NGO_Campaign.org_id == current_user.org_id)
    campaign_count = (await db.execute(campaign_stmt)).scalar() or 0
    
    # 2. Count Inventory Items
    inventory_stmt = select(func.count(Inventory.id)).where(Inventory.org_id == current_user.org_id)
    inventory_count = (await db.execute(inventory_stmt)).scalar() or 0
    
    # 3. Count Volunteers
    volunteer_stmt = select(func.count(Volunteer.id)).where(Volunteer.org_id == current_user.org_id)
    volunteer_count = (await db.execute(volunteer_stmt)).scalar() or 0
    
    return {
        "total_campaigns": campaign_count,
        "total_inventory": inventory_count,
        "total_volunteers": volunteer_count
    }

@router.post("/me/image")
async def upload_profile_image(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Securely upload and update any logged-in user's profile image."""
    # 1. Validate File Type
    if file.content_type not in ["image/jpeg", "image/png", "image/webp"]:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG and WEBP images are supported")

    # 2. Upload to Cloudinary
    try:
        new_url = cloudinary_service.upload_image(file.file, folder="profiles")
        if not new_url:
            raise HTTPException(status_code=500, detail="Cloudinary upload failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save image: {str(e)}")

    # 3. Update User Record
    current_user.profile_image_url = new_url
    await db.commit()

    return {"profile_image_url": new_url, "message": "Profile image updated successfully"}

@router.delete("/me/image")
async def remove_profile_image(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Revert user profile picture to default. 
    Deletes the physical file if it exists in the profiles directory.
    """
    if not current_user.profile_image_url:
        return {"message": "No profile image to remove"}

    # 1. Cloudinary Cleanup
    if current_user.profile_image_url and "cloudinary" in current_user.profile_image_url:
        cloudinary_service.delete_image(current_user.profile_image_url)
    
    # 2. Local Cleanup Fallback (Legacy)
    elif current_user.profile_image_url and "/static/profiles/" in current_user.profile_image_url:
        filename = current_user.profile_image_url.split("/")[-1]
        static_dir = os.path.join("backend", "app", "static", "profiles")
        file_path = os.path.join(static_dir, filename)
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"[WARNING] Local cleanup failed: {e}")

    # 2. Reset DB Record
    current_user.profile_image_url = None
    await db.commit()

    return {"message": "Profile image removed and reverted to default"}

@router.patch("/me", response_model=UserRead)
async def update_my_profile(
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update profile details (e.g., full_name, email) for the authenticated user."""
    if data.full_name is not None:
        current_user.full_name = data.full_name
    
    if data.email is not None:
        # Simple check for email duplication could be added here if needed, 
        # but the DB unique constraint will catch it anyway.
        current_user.email = data.email
    
    await db.commit()
    await db.refresh(current_user)
    return current_user

@router.post("/me/change-password")
async def change_my_password(
    data: PasswordChange,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Securely change the authenticated user's password using old password verification."""
    # 1. Verify old password
    if not verify_password(data.old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password"
        )
    
    # 2. Update to new password
    current_user.hashed_password = get_password_hash(data.new_password)
    await db.commit()
    
    return {"status": "success", "message": "Password updated successfully"}

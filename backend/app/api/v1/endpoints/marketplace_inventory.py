from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from backend.app.database import get_db
from backend.app.models import MarketplaceInventory, User
from backend.app.api.deps import get_current_user
from pydantic import BaseModel
from datetime import datetime
from typing import List, Dict

# --- Schemas ---

class MarketplaceInventoryResponse(BaseModel):
    id: int
    org_id: int
    item_name: str
    quantity: float
    unit: str
    collected_at: datetime

    class Config:
        from_attributes = True

class MarketplaceStats(BaseModel):
    total_items_recovered: int
    item_breakdown: Dict[str, int]

# --- Router ---

router = APIRouter()

@router.get("/", response_model=List[MarketplaceInventoryResponse])
async def list_marketplace_inventory(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all resources recovered via the Marketplace for the current NGO.
    """
    stmt = (
        select(MarketplaceInventory)
        .where(MarketplaceInventory.org_id == current_user.org_id)
        .order_by(MarketplaceInventory.collected_at.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()

@router.get("/stats", response_model=MarketplaceStats)
async def get_marketplace_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Summarize the total impact made via Marketplace recovery.
    """
    # 1. Total Count
    count_stmt = select(func.count(MarketplaceInventory.id)).where(MarketplaceInventory.org_id == current_user.org_id)
    total_count = (await db.execute(count_stmt)).scalar() or 0

    # 2. Breakdown by type
    breakdown_stmt = (
        select(MarketplaceInventory.item_name, func.count(MarketplaceInventory.id))
        .where(MarketplaceInventory.org_id == current_user.org_id)
        .group_by(MarketplaceInventory.item_name)
    )
    breakdown_result = await db.execute(breakdown_stmt)
    breakdown = {name: count for name, count in breakdown_result}

    return {
        "total_items_recovered": total_count,
        "item_breakdown": breakdown
    }

@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recovery_record(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Remove a recovery record (Coordinators only).
    Useful for cleaning up test data or erroneous entries.
    """
    stmt = select(MarketplaceInventory).where(
        MarketplaceInventory.id == item_id,
        MarketplaceInventory.org_id == current_user.org_id
    )
    result = await db.execute(stmt)
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=404, detail="Recovery record not found")

    await db.delete(item)
    await db.commit()

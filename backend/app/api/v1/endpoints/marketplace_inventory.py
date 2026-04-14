from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from backend.app.database import get_db
from backend.app.models import MarketplaceInventory, User, Inventory, AuditTrail
from backend.app.api.deps import get_current_user
from backend.app.utils.fuzzy import find_best_matches
from pydantic import BaseModel
from datetime import datetime
from typing import List, Dict, Optional

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

class TransferRequest(BaseModel):
    inventory_id: Optional[int] = None # If provided, merge into this ID. If None, add as new.
    category: Optional[str] = "OTHERS"

class Suggestion(BaseModel):
    id: int
    item_name: str
    score: float

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

@router.get("/{item_id}/suggestions", response_model=List[Suggestion])
async def get_transfer_suggestions(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Find existing inventory items that might match this marketplace item.
    """
    # 1. Get the marketplace item
    m_item = (await db.execute(
        select(MarketplaceInventory).where(
            MarketplaceInventory.id == item_id,
            MarketplaceInventory.org_id == current_user.org_id
        )
    )).scalar_one_or_none()
    
    if not m_item:
        raise HTTPException(status_code=404, detail="Marketplace item not found")

    # 2. Get all existing inventory items for this org
    inv_items = (await db.execute(
        select(Inventory).where(Inventory.org_id == current_user.org_id)
    )).scalars().all()
    
    # 3. Fuzzy match
    choices = {i.item_name: i.id for i in inv_items}
    matches = find_best_matches(m_item.item_name, list(choices.keys()), threshold=0.4)
    
    return [
        {"id": choices[name], "item_name": name, "score": score}
        for name, score in matches
    ]

@router.post("/{item_id}/transfer")
async def transfer_to_inventory(
    item_id: int,
    data: TransferRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Transfer an item from Marketplace Recovery to Main NGO Inventory.
    """
    # 1. Get marketplace item
    stmt = select(MarketplaceInventory).where(
        MarketplaceInventory.id == item_id,
        MarketplaceInventory.org_id == current_user.org_id
    )
    result = await db.execute(stmt)
    m_item = result.scalar_one_or_none()
    
    if not m_item:
        raise HTTPException(status_code=404, detail="Marketplace item not found")

    target_inv = None
    
    # 2. Find or create target inventory item
    if data.inventory_id:
        target_inv = (await db.execute(
            select(Inventory).where(
                Inventory.id == data.inventory_id,
                Inventory.org_id == current_user.org_id
            )
        )).scalar_one_or_none()
        
        if not target_inv:
            raise HTTPException(status_code=404, detail="Target inventory item not found")
        
        target_inv.quantity += m_item.quantity
    else:
        # Create as new item
        target_inv = Inventory(
            org_id=current_user.org_id,
            item_name=m_item.item_name,
            quantity=m_item.quantity,
            unit=m_item.unit,
            category=data.category or "OTHERS"
        )
        db.add(target_inv)
    
    # 3. Log Audit Trail
    audit = AuditTrail(
        org_id=current_user.org_id,
        actor_id=current_user.id,
        event_type="INVENTORY_TRANSFERRED",
        notes=f"Transferred {m_item.quantity} {m_item.unit} of '{m_item.item_name}' from Marketplace to Main Inventory."
    )
    db.add(audit)
    
    # 4. Clean up
    await db.delete(m_item)
    await db.commit()
    
    return {"status": "success", "message": f"Successfully transferred '{m_item.item_name}' to main inventory."}

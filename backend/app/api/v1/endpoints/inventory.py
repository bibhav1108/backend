from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.database import get_db
from backend.app.models import Inventory, User
from backend.app.api.deps import get_current_user
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()

# --- Schemas ---
class InventoryBase(BaseModel):
    item_name: str
    quantity: float
    unit: str
    category: str = "OTHERS"

class InventoryCreate(InventoryBase):
    pass

class InventoryUpdate(BaseModel):
    quantity: Optional[float] = None
    item_name: Optional[str] = None
    unit: Optional[str] = None
    category: Optional[str] = None

class InventoryResponse(InventoryBase):
    id: int
    org_id: int
    reserved_quantity: float = 0.0

    class Config:
        from_attributes = True

# --- Endpoints ---

@router.get("/", response_model=List[InventoryResponse])
async def list_inventory(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all inventory items for the current NGO."""
    stmt = select(Inventory).where(Inventory.org_id == current_user.org_id)
    result = await db.execute(stmt)
    return result.scalars().all()

@router.post("/", response_model=InventoryResponse, status_code=status.HTTP_201_CREATED)
async def add_inventory_item(
    data: InventoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Add a new inventory item."""
    # Check if item already exists for this org
    stmt = select(Inventory).where(
        Inventory.org_id == current_user.org_id,
        Inventory.item_name == data.item_name
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Item '{data.item_name}' already exists. Use PATCH to update quantity."
        )

    item = Inventory(
        org_id=current_user.org_id,
        **data.model_dump()
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item

@router.patch("/{item_id}", response_model=InventoryResponse)
async def update_inventory_item(
    item_id: int,
    data: InventoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update inventory item quantity or details."""
    stmt = select(Inventory).where(
        Inventory.id == item_id,
        Inventory.org_id == current_user.org_id
    )
    result = await db.execute(stmt)
    item = result.scalar_one_or_none()
    
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(item, field, value)
    
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_inventory_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete an inventory item by ID.
    
    Returns 404 if the item does not exist or does not belong to the current NGO.
    Returns 409 if the item has a reserved quantity (currently tied to an active dispatch/campaign).
    """
    stmt = select(Inventory).where(
        Inventory.id == item_id,
        Inventory.org_id == current_user.org_id
    )
    result = await db.execute(stmt)
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    if item.reserved_quantity > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot delete '{item.item_name}': it has {item.reserved_quantity} units currently reserved. "
                   "Release the reservation before deleting."
        )

    await db.delete(item)
    await db.commit()

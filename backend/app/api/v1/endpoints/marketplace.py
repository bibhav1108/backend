from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from backend.app.database import get_db
from backend.app.models import (
    MarketplaceNeed, 
    Organization, 
    NeedType, 
    NeedStatus, 
    Urgency, 
    User, 
    MarketplaceAlert
)
from backend.app.api.deps import get_current_user, get_current_user_optional
from backend.app.services.telegram_service import telegram_service
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional

# --- Schemas ---

class MarketplaceNeedCreate(BaseModel):
    type: NeedType
    description: str = Field(..., example="50 food packets ready for transport")
    quantity: str = Field(..., example="50 packets")
    pickup_address: str = Field(..., example="Hotel Clarks, Marg Road, Lucknow")
    urgency: Urgency = Urgency.MEDIUM
    pickup_deadline: Optional[datetime] = None
    org_id: Optional[int] = None
    marketplace_alert_id: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

class MarketplaceNeedResponse(BaseModel):
    id: int
    org_id: Optional[int]
    type: NeedType
    description: str
    quantity: str
    pickup_address: str
    urgency: Urgency
    status: NeedStatus
    marketplace_alert_id: Optional[int]
    latitude: Optional[float]
    longitude: Optional[float]
    pickup_deadline: Optional[datetime]
    created_at: datetime

class MarketplaceAlertResponse(BaseModel):
    id: int
    chat_id: str
    message_body: str
    donor_name: Optional[str]
    phone_number: Optional[str]
    item: Optional[str]
    quantity: Optional[str]
    location: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    notes: Optional[str]
    created_at: datetime
    is_confirmed: bool
    is_processed: bool

    class Config:
        from_attributes = True

# --- Router ---

router = APIRouter()

@router.post("/", response_model=MarketplaceNeedResponse, status_code=status.HTTP_201_CREATED)
async def create_marketplace_need(
    data: MarketplaceNeedCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Create a new Marketplace Need. 
    This is the core of the 'Speed Layer' - Reactive donor alerts.
    """
    need_data = data.model_dump()
    if current_user:
        need_data["org_id"] = current_user.org_id

    need = MarketplaceNeed(**need_data)
    db.add(need)
    await db.commit()
    await db.refresh(need)
    return need

@router.get("/", response_model=List[MarketplaceNeedResponse])
async def list_marketplace_needs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List Marketplace Needs visible to the current NGO:
    1. Needs belonging to their NGO.
    2. Public/Global needs (unclaimed) from the marketplace.
    """
    stmt = select(MarketplaceNeed).where(
        or_(
            MarketplaceNeed.org_id == current_user.org_id,
            MarketplaceNeed.org_id == None
        )
    )
    result = await db.execute(stmt)
    return result.scalars().all()

@router.post("/{need_id}/claim", response_model=MarketplaceNeedResponse)
async def claim_marketplace_need(
    need_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Claim a global marketplace need for the current NGO.
    Strictly Speed Layer: First-come-first-serve.
    """
    stmt = select(MarketplaceNeed).where(MarketplaceNeed.id == need_id)
    result = await db.execute(stmt)
    need = result.scalar_one_or_none()
    
    if not need:
        raise HTTPException(status_code=404, detail="Marketplace need not found")
    
    if need.org_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="This need has already been claimed by another NGO."
        )
    
    need.org_id = current_user.org_id
    await db.commit()
    await db.refresh(need)

    # Notify Donor via Marketplace Alert link
    if need.marketplace_alert_id:
        stmt_alert = select(MarketplaceAlert).where(MarketplaceAlert.id == need.marketplace_alert_id)
        alert = (await db.execute(stmt_alert)).scalar_one_or_none()
        if alert:
            stmt_org = select(Organization).where(Organization.id == current_user.org_id)
            org = (await db.execute(stmt_org)).scalar_one_or_none()
            org_name = org.name if org else "A local NGO"
            
            msg = (
                f"📢 *Update on your Contribution!*\n\n"
                f"NGO *{org_name}* has claimed your surplus report! 🤝\n"
                f"They are now assigning a dedicated volunteer to reach you for the pickup. Thank you for your generosity!"
            )
            await telegram_service.send_message(chat_id=alert.chat_id, text=msg)

    return need

@router.get("/alerts", response_model=List[MarketplaceAlertResponse])
async def list_marketplace_alerts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all CONFIRMED and unprocessed surplus alerts from the Telegram bot for NGOs to claim.
    """
    stmt = select(MarketplaceAlert).where(
        MarketplaceAlert.is_confirmed == True,
        MarketplaceAlert.is_processed == False
    ).order_by(MarketplaceAlert.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()

@router.post("/alerts/{alert_id}/convert", response_model=MarketplaceNeedResponse)
async def convert_alert_to_marketplace_need(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Automated Conversion: Transforms a raw MarketplaceAlert into a formal MarketplaceNeed.
    No inventory locking involved (Marketplace is reactive).
    """
    stmt = select(MarketplaceAlert).where(MarketplaceAlert.id == alert_id)
    result = await db.execute(stmt)
    alert = result.scalar_one_or_none()
    
    if not alert:
        raise HTTPException(status_code=404, detail="Marketplace alert not found")
        
    if alert.is_processed:
        raise HTTPException(status_code=400, detail="This alert has already been processed.")

    # Create the MarketplaceNeed using structured AI data if available
    need_description = alert.notes if (alert.notes and alert.notes != "N/A") else alert.message_body
    
    new_need = MarketplaceNeed(
        org_id=current_user.org_id,
        marketplace_alert_id=alert.id,
        type=alert.predicted_type or NeedType.FOOD,
        description=f"ITEM: {alert.item or 'Not Specified'} | NOTES: {need_description}",
        quantity=alert.quantity or "As per report",
        pickup_address=alert.location or "Check donor contact",
        latitude=alert.latitude,
        longitude=alert.longitude,
        urgency=alert.predicted_urgency or Urgency.HIGH,
        status=NeedStatus.OPEN
    )
    
    db.add(new_need)
    alert.is_processed = True
    await db.commit()
    await db.refresh(new_need)
    
    # Notify Donor
    stmt_org = select(Organization).where(Organization.id == current_user.org_id)
    org = (await db.execute(stmt_org)).scalar_one_or_none()
    org_name = org.name if org else "A local NGO"

    msg = (
        f"📢 *Good News HERO!*\n\n"
        f"NGO *{org_name}* has officially accepted your mission report! ✨🤝\n"
        f"Your contribution is vital. A volunteer will be assigned very soon to collect the items."
    )
    await telegram_service.send_message(chat_id=alert.chat_id, text=msg)
    
    return new_need

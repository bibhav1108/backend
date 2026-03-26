from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from backend.app.database import get_db
from backend.app.models import Need, Organization, NeedType, NeedStatus, Urgency, User , SurplusAlert
from backend.app.api.deps import get_current_user, get_current_user_optional
from backend.app.services.telegram_service import telegram_service
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional

# --- Schemas ---

class NeedCreate(BaseModel):
    type: NeedType
    description: str = Field(..., example="50 food packets ready for transport")
    quantity: str = Field(..., example="50 packets")
    pickup_address: str = Field(..., example="Hotel Clarks, Marg Road, Lucknow")
    urgency: Urgency = Urgency.MEDIUM
    pickup_deadline: Optional[datetime] = None
    org_id: Optional[int] = None  # Optional for donor/public alerts
    surplus_alert_id: Optional[int] = None  # To link with Telegram bot alerts

class NeedResponse(BaseModel):
    id: int
    org_id: Optional[int]
    type: NeedType
    description: str
    quantity: str
    pickup_address: str
    urgency: Urgency
    status: NeedStatus
    surplus_alert_id: Optional[int]
    pickup_deadline: Optional[datetime]
    created_at: datetime

class SurplusAlertResponse(BaseModel):
    id: int
    chat_id: str
    message_body: str
    donor_name: Optional[str]
    created_at: datetime
    is_processed: bool

    class Config:
        from_attributes = True

# --- Router ---

router = APIRouter()

@router.post("/", response_model=NeedResponse, status_code=status.HTTP_201_CREATED)
async def create_need(
    data: NeedCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)  # Optional for V1.5 Marketplace
):
    """
    Create a new Need. 
    If created by a coordinator, org_id is auto-set. 
    If created by a donor (unauthenticated for now), org_id remains NULL (Marketplace).
    """
    need_data = data.model_dump()
    if current_user:
        need_data["org_id"] = current_user.org_id

    need = Need(**need_data)
    db.add(need)
    await db.commit()
    await db.refresh(need)
    return need

@router.get("/", response_model=List[NeedResponse])
async def list_needs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List Needs visible to the current NGO:
    1. Needs belonging to their NGO.
    2. Public/Global needs (org_id is NULL) that haven't been claimed.
    """
    stmt = select(Need).where(
        or_(
            Need.org_id == current_user.org_id,
            Need.org_id == None
        )
    )
    result = await db.execute(stmt)
    return result.scalars().all()

@router.post("/{need_id}/claim", response_model=NeedResponse)
async def claim_need(
    need_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Claim a global/public need for the current NGO.
    First-come-first-serve logic.
    """
    stmt = select(Need).where(Need.id == need_id)
    result = await db.execute(stmt)
    need = result.scalar_one_or_none()
    
    if not need:
        raise HTTPException(status_code=404, detail="Need not found")
    
    if need.org_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="This need has already been claimed by another NGO."
        )
    
    need.org_id = current_user.org_id
    # Log the claim in real world would be good
    await db.commit()
    await db.refresh(need)

    # Notify Donor if linked
    if need.surplus_alert_id:
        stmt_alert = select(SurplusAlert).where(SurplusAlert.id == need.surplus_alert_id)
        alert = (await db.execute(stmt_alert)).scalar_one_or_none()
        if alert:
            stmt_org = select(Organization).where(Organization.id == current_user.org_id)
            org = (await db.execute(stmt_org)).scalar_one_or_none()
            org_name = org.name if org else "A local NGO"
            
            msg = (
                f"📢 *Update on your Donation!*\n\n"
                f"NGO *{org_name}* has claimed your surplus report! 🤝\n"
                f"They are now assigning a volunteer for the pickup. Please stay tuned for the next update."
            )
            await telegram_service.send_message(chat_id=alert.chat_id, text=msg)

    return need
@router.get("/surplus-alerts", response_model=List[SurplusAlertResponse])
async def list_surplus_alerts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all unprocessed surplus alerts from the Telegram bot for NGOs to claim/review.
    """
    stmt = select(SurplusAlert).where(SurplusAlert.is_processed == False).order_by(SurplusAlert.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()

    alert.is_processed = True
    await db.commit()

    # Notify Donor
    stmt_org = select(Organization).where(Organization.id == current_user.org_id)
    org = (await db.execute(stmt_org)).scalar_one_or_none()
    org_name = org.name if org else "A local NGO"

    msg = (
        f"📢 *NGO Interested!*\n\n"
        f"*{org_name}* is reviewing your surplus report. 🤝\n"
        f"They will assign a volunteer shortly if the items match their needs."
    )
    await telegram_service.send_message(chat_id=alert.chat_id, text=msg)

    return {"status": "success", "message": "Alert marked as processed"}

@router.post("/surplus-alerts/{alert_id}/convert", response_model=NeedResponse)
async def convert_surplus_to_need(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Automated Conversion: Transforms a raw SurplusAlert into a formal NGO Need.
    Returns the created Need so the dashboard can show/edit it.
    """
    stmt = select(SurplusAlert).where(SurplusAlert.id == alert_id)
    result = await db.execute(stmt)
    alert = result.scalar_one_or_none()
    
    if not alert:
        raise HTTPException(status_code=404, detail="Surplus alert not found")
        
    if alert.is_processed:
        raise HTTPException(status_code=400, detail="This alert has already been processed.")

    # 1. Create the Need
    # We attempt to parse basics from the message body if possible, or just dump it to description
    need_description = f"Donation from {alert.donor_name or 'Donor'}: {alert.message_body}"
    
    new_need = Need(
        org_id=current_user.org_id,
        surplus_alert_id=alert.id,
        type=NeedType.FOOD, # Default for surplus
        description=need_description,
        quantity="As per report", # Placeholder to be edited by NGO
        pickup_address="Check donor contact", # Placeholder
        urgency=Urgency.HIGH, # Surplus is usually time-sensitive
        status=NeedStatus.PENDING
    )
    
    db.add(new_need)
    alert.is_processed = True
    await db.commit()
    await db.refresh(new_need)
    
    # 2. Notify Donor (Rich notification)
    stmt_org = select(Organization).where(Organization.id == current_user.org_id)
    org = (await db.execute(stmt_org)).scalar_one_or_none()
    org_name = org.name if org else "A local NGO"

    msg = (
        f"📢 *Great News!*\n\n"
        f"NGO *{org_name}* has officially accepted your donation report! ✨🤝\n"
        f"They are now preparing for pickup. A volunteer will be assigned very soon."
    )
    await telegram_service.send_message(chat_id=alert.chat_id, text=msg)
    
    return new_need

from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Boolean, Enum as SQLEnum, JSON, UniqueConstraint
from sqlalchemy.orm import relationship, Mapped, mapped_column
from geoalchemy2 import Geometry
from backend.app.database import Base
import enum
from datetime import datetime, timedelta, timezone
from typing import List, Optional

# --- Enums ---
class NeedType(str, enum.Enum):
    FOOD = "FOOD"
    WATER = "WATER"
    KIT = "KIT"
    BLANKET = "BLANKET"
    MEDICAL = "MEDICAL"
    VEHICLE = "VEHICLE"
    OTHER = "OTHER"

class NeedStatus(str, enum.Enum):
    OPEN = "OPEN"
    DISPATCHED = "DISPATCHED"
    OTP_SENT = "OTP_SENT"
    COMPLETED = "COMPLETED"
    CLOSED = "CLOSED"

class TrustTier(str, enum.Enum):
    UNVERIFIED = "UNVERIFIED"
    ID_VERIFIED = "ID_VERIFIED"
    FIELD_VERIFIED = "FIELD_VERIFIED"

class Urgency(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

class DispatchStatus(str, enum.Enum):
    SENT = "SENT"        # Alert sent to volunteer
    ACCEPTED = "ACCEPTED" # Volunteer accepted the mission
    COMPLETED = "COMPLETED" # OTP verified by donor
    FAILED = "FAILED"     # OTP failed 3 times or cancelled

class CampaignStatus(str, enum.Enum):
    PLANNED = "PLANNED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"

class CampaignType(str, enum.Enum):
    HEALTH = "HEALTH"
    EDUCATION = "EDUCATION"
    BASIC_NEEDS = "BASIC_NEEDS"
    AWARENESS = "AWARENESS"
    EMERGENCY = "EMERGENCY"
    ENVIRONMENT = "ENVIRONMENT"
    SKILLS = "SKILLS"
    OTHER = "OTHER"

class CampaignParticipationStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class NotificationType(str, enum.Enum):
    DONOR_ALERT = "DONOR_ALERT"           # New report from bot
    MISSION_ACCEPTED = "MISSION_ACCEPTED" # Volunteer claimed a mission
    MISSION_COMPLETED = "MISSION_COMPLETED" # OTP Verified
    MISSION_CANCELLED = "MISSION_CANCELLED" # Volunteer cancelled
    CAMPAIGN_INTEREST = "CAMPAIGN_INTEREST" # Volunteer opted-in
    SYSTEM = "SYSTEM"                      # General broadcast

# --- Models ---

class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(index=True)
    contact_phone: Mapped[str] = mapped_column(unique=True)
    contact_email: Mapped[str] = mapped_column(unique=True)
    status: Mapped[str] = mapped_column(default="pending")  # pending/active
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

    volunteers: Mapped[List["Volunteer"]] = relationship(back_populates="organization")
    marketplace_needs: Mapped[List["MarketplaceNeed"]] = relationship(back_populates="organization")
    users: Mapped[List["User"]] = relationship(back_populates="organization")
    inventory: Mapped[List["Inventory"]] = relationship(back_populates="organization")
    marketplace_inventory: Mapped[List["MarketplaceInventory"]] = relationship(back_populates="organization")
    campaigns: Mapped[List["NGO_Campaign"]] = relationship(back_populates="organization")

    # --- Newsletter Broadcast Limits ---
    last_broadcast_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    daily_broadcast_count: Mapped[int] = mapped_column(default=0)

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    email: Mapped[str] = mapped_column(unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column()
    full_name: Mapped[Optional[str]] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

    organization: Mapped["Organization"] = relationship(back_populates="users")

class Volunteer(Base):
    __tablename__ = "volunteers"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column()
    phone_number: Mapped[str] = mapped_column(unique=True, index=True)
    telegram_chat_id: Mapped[Optional[str]] = mapped_column(unique=True, index=True, nullable=True)
    telegram_active: Mapped[bool] = mapped_column(default=False)
    
    trust_tier: Mapped[TrustTier] = mapped_column(SQLEnum(TrustTier), default=TrustTier.UNVERIFIED)
    skills: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    zone: Mapped[Optional[str]] = mapped_column(nullable=True)
    
    location = Column(Geometry(geometry_type='POINT', srid=4326), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

    organization: Mapped["Organization"] = relationship(back_populates="volunteers")
    stats: Mapped["VolunteerStats"] = relationship(back_populates="volunteer", uselist=False)

class VolunteerStats(Base):
    __tablename__ = "volunteer_stats"

    volunteer_id: Mapped[int] = mapped_column(ForeignKey("volunteers.id"), primary_key=True)
    completions: Mapped[int] = mapped_column(default=0)
    no_shows: Mapped[int] = mapped_column(default=0)
    hours_served: Mapped[float] = mapped_column(default=0.0)
    
    last_dispatch_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    volunteer: Mapped["Volunteer"] = relationship(back_populates="stats")

class MarketplaceAlert(Base):
    __tablename__ = "marketplace_alerts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    chat_id: Mapped[str] = mapped_column(index=True)
    message_body: Mapped[str] = mapped_column()
    phone_number: Mapped[Optional[str]] = mapped_column(nullable=True)
    donor_name: Mapped[Optional[str]] = mapped_column(nullable=True)
    
    # Structured AI Fields for Dashboard Visibility
    item: Mapped[Optional[str]] = mapped_column(nullable=True)
    quantity: Mapped[Optional[str]] = mapped_column(nullable=True)
    location: Mapped[Optional[str]] = mapped_column(nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    is_confirmed: Mapped[bool] = mapped_column(default=False) # Donor must approve AI summary
    is_processed: Mapped[bool] = mapped_column(default=False) # NGO has converted to Need

    # AI Predictions for easier NGO conversion
    predicted_type: Mapped[Optional[NeedType]] = mapped_column(SQLEnum(NeedType), nullable=True)
    predicted_urgency: Mapped[Optional[Urgency]] = mapped_column(SQLEnum(Urgency), nullable=True)

    marketplace_needs: Mapped[List["MarketplaceNeed"]] = relationship(back_populates="marketplace_alert")

class MarketplaceNeed(Base):
    __tablename__ = "marketplace_needs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    org_id: Mapped[Optional[int]] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    marketplace_alert_id: Mapped[Optional[int]] = mapped_column(ForeignKey("marketplace_alerts.id"), nullable=True)
    type: Mapped[NeedType] = mapped_column(SQLEnum(NeedType))
    description: Mapped[str] = mapped_column()
    quantity: Mapped[str] = mapped_column()
    pickup_address: Mapped[str] = mapped_column()
    urgency: Mapped[Urgency] = mapped_column(SQLEnum(Urgency), default=Urgency.MEDIUM)
    status: Mapped[NeedStatus] = mapped_column(SQLEnum(NeedStatus), default=NeedStatus.OPEN)
    pickup_deadline: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

    organization: Mapped["Organization"] = relationship(back_populates="marketplace_needs")
    marketplace_alert: Mapped["MarketplaceAlert"] = relationship(back_populates="marketplace_needs")
    dispatches: Mapped[List["MarketplaceDispatch"]] = relationship(back_populates="marketplace_need")

class MarketplaceDispatch(Base):
    __tablename__ = "marketplace_dispatches"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    marketplace_need_id: Mapped[int] = mapped_column(ForeignKey("marketplace_needs.id"))
    volunteer_id: Mapped[int] = mapped_column(ForeignKey("volunteers.id"))
    
    otp_hash: Mapped[Optional[str]] = mapped_column(nullable=True)
    otp_used: Mapped[bool] = mapped_column(default=False)
    otp_expires_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    otp_attempts: Mapped[int] = mapped_column(default=0)
    
    status: Mapped[DispatchStatus] = mapped_column(SQLEnum(DispatchStatus), default=DispatchStatus.SENT)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

    marketplace_need: Mapped["MarketplaceNeed"] = relationship(back_populates="dispatches")
    volunteer: Mapped["Volunteer"] = relationship()

class NGO_Campaign(Base):
    __tablename__ = "ngo_campaigns"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(index=True)
    description: Mapped[Optional[str]] = mapped_column(nullable=True)
    type: Mapped[CampaignType] = mapped_column(SQLEnum(CampaignType), default=CampaignType.OTHER)
    target_quantity: Mapped[Optional[str]] = mapped_column(nullable=True)
    items: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[CampaignStatus] = mapped_column(SQLEnum(CampaignStatus), default=CampaignStatus.PLANNED)
    
    start_time: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    end_time: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    volunteers_required: Mapped[int] = mapped_column(default=0)
    required_skills: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    location_address: Mapped[Optional[str]] = mapped_column(nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

    organization: Mapped["Organization"] = relationship(back_populates="campaigns")
    participants: Mapped[List["MissionTeam"]] = relationship(back_populates="campaign")

class MissionTeam(Base):
    __tablename__ = "mission_teams"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("ngo_campaigns.id"))
    volunteer_id: Mapped[int] = mapped_column(ForeignKey("volunteers.id"))
    status: Mapped[CampaignParticipationStatus] = mapped_column(SQLEnum(CampaignParticipationStatus), default=CampaignParticipationStatus.PENDING)
    joined_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

    campaign: Mapped["NGO_Campaign"] = relationship(back_populates="participants")
    volunteer: Mapped["Volunteer"] = relationship()

class Inventory(Base):
    __tablename__ = "inventory"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    item_name: Mapped[str] = mapped_column(index=True)
    quantity: Mapped[float] = mapped_column(default=0.0)
    unit: Mapped[str] = mapped_column()
    category: Mapped[str] = mapped_column(default="OTHERS")
    reserved_quantity: Mapped[float] = mapped_column(default=0.0)
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    organization: Mapped["Organization"] = relationship(back_populates="inventory")

class MarketplaceInventory(Base):
    __tablename__ = "marketplace_inventory"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    item_name: Mapped[str] = mapped_column(index=True)
    quantity: Mapped[float] = mapped_column(default=0.0)
    unit: Mapped[str] = mapped_column()
    collected_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

    organization: Mapped["Organization"] = relationship(back_populates="marketplace_inventory")

class TelegramMessage(Base):
    __tablename__ = "telegram_messages"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    chat_id: Mapped[str] = mapped_column(index=True)
    message_id: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

class InboundMessage(Base):
    """
    Deduplication Store: Tracks incoming message IDs to prevent double-processing
    during Telegram retries or rapid user clicks.
    """
    __tablename__ = "inbound_messages"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    chat_id: Mapped[str] = mapped_column(index=True)
    message_id: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint('chat_id', 'message_id', name='_chat_message_uc'),)

class AuditTrail(Base) :
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    org_id: Mapped[Optional[int]] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    actor_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    event_type: Mapped[str] = mapped_column()
    target_id: Mapped[Optional[str]] = mapped_column(nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    org_id: Mapped[Optional[int]] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    
    type: Mapped[NotificationType] = mapped_column(SQLEnum(NotificationType))
    title: Mapped[str] = mapped_column()
    message: Mapped[str] = mapped_column()
    priority: Mapped[str] = mapped_column(default="INFO") # INFO, SUCCESS, WARNING, ERROR
    
    is_read: Mapped[bool] = mapped_column(default=False)
    data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True) # {"alert_id": 1, "campaign_id": 2}
    
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

    organization: Mapped["Organization"] = relationship()

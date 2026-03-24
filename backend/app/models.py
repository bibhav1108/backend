from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Boolean, Enum as SQLEnum, JSON
from sqlalchemy.orm import relationship, Mapped, mapped_column
from geoalchemy2 import Geometry
from backend.app.database import Base
import enum
from datetime import datetime
from typing import List, Optional

# --- Enums ---
class NeedType(str, enum.Enum):
    FOOD = "FOOD"
    WATER = "WATER"
    KIT = "KIT"
    BLANKET = "BLANKET"
    MEDICAL = "MEDICAL"
    VEHICLE = "VEHICLE"

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
    SENT = "SENT"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"

# --- Models ---

class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(index=True)
    contact_phone: Mapped[str] = mapped_column(unique=True)
    contact_email: Mapped[str] = mapped_column(unique=True)
    status: Mapped[str] = mapped_column(default="pending")  # pending/active
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    volunteers: Mapped[List["Volunteer"]] = relationship(back_populates="organization")
    needs: Mapped[List["Need"]] = relationship(back_populates="organization")

class Volunteer(Base):
    __tablename__ = "volunteers"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column()
    phone_number: Mapped[str] = mapped_column(unique=True, index=True)
    whatsapp_active: Mapped[bool] = mapped_column(default=False)
    
    # [V3 Future-Proofing]
    trust_tier: Mapped[TrustTier] = mapped_column(SQLEnum(TrustTier), default=TrustTier.UNVERIFIED)
    skills: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)  # Array of skills
    zone: Mapped[Optional[str]] = mapped_column(nullable=True)  # Operational zone
    
    # [PostGIS Future-Proofing]
    # Geometry('POINT', 4326) stores Location as (Longitude, Latitude)
    location = Column(Geometry(geometry_type='POINT', srid=4326), nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    organization: Mapped["Organization"] = relationship(back_populates="volunteers")
    stats: Mapped["VolunteerStats"] = relationship(back_populates="volunteer", uselist=False)

class VolunteerStats(Base):
    __tablename__ = "volunteer_stats"

    volunteer_id: Mapped[int] = mapped_column(ForeignKey("volunteers.id"), primary_key=True)
    completions: Mapped[int] = mapped_column(default=0)
    no_shows: Mapped[int] = mapped_column(default=0)
    
    # [V3 Future-Proofing]
    hours_served: Mapped[float] = mapped_column(default=0.0)
    
    last_dispatch_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)

    volunteer: Mapped["Volunteer"] = relationship(back_populates="stats")

class Need(Base):
    __tablename__ = "needs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    type: Mapped[NeedType] = mapped_column(SQLEnum(NeedType))
    description: Mapped[str] = mapped_column()
    quantity: Mapped[str] = mapped_column()  # e.g., "50 packets"
    pickup_address: Mapped[str] = mapped_column()
    urgency: Mapped[Urgency] = mapped_column(SQLEnum(Urgency), default=Urgency.MEDIUM)
    status: Mapped[NeedStatus] = mapped_column(SQLEnum(NeedStatus), default=NeedStatus.OPEN)
    pickup_deadline: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    organization: Mapped["Organization"] = relationship(back_populates="needs")
    dispatches: Mapped[List["Dispatch"]] = relationship(back_populates="need")

class Dispatch(Base):
    __tablename__ = "dispatches"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    need_id: Mapped[int] = mapped_column(ForeignKey("needs.id"))
    volunteer_id: Mapped[int] = mapped_column(ForeignKey("volunteers.id"))
    
    # [OTP Security]
    otp_hash: Mapped[Optional[str]] = mapped_column(nullable=True)
    otp_used: Mapped[bool] = mapped_column(default=False)
    otp_expires_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    
    status: Mapped[DispatchStatus] = mapped_column(SQLEnum(DispatchStatus), default=DispatchStatus.SENT)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    need: Mapped["Need"] = relationship(back_populates="dispatches")

class AuditTrail(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    org_id: Mapped[Optional[int]] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    actor_id: Mapped[Optional[int]] = mapped_column(nullable=True)  # User or Coordinator ID
    event_type: Mapped[str] = mapped_column()  # e.g., "DISPATCH_TRIGGERED", "NEED_CREATED"
    target_id: Mapped[Optional[str]] = mapped_column(nullable=True) # ID of need/volunteer affected
    notes: Mapped[Optional[str]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

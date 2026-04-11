from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
from backend.app.models import TrustTier

class VolunteerCreate(BaseModel):
    name: str = Field(..., example="Rohit Sharma")
    phone_number: str = Field(..., example="+919876543210")
    zone: Optional[str] = Field(None, example="Lucknow East")
    skills: Optional[List[str]] = Field(default=[], example=["food", "logistics"])

class VolunteerResponse(BaseModel):
    id: int
    name: str
    phone_number: str
    telegram_active: bool
    telegram_chat_id: Optional[str] = None
    org_id: int
    trust_tier: TrustTier
    trust_score: int = 0
    id_verified: bool = False
    
    # Stats integrated for Dashboard view
    completions: int = 0
    no_shows: int = 0

    class Config:
        from_attributes = True

class TrustUpdate(BaseModel):
    trust_tier: TrustTier

class VolunteerProfileUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    skills: Optional[List[str]] = None
    zone: Optional[str] = None

class VolunteerProfileResponse(BaseModel):
    id: int
    name: str
    phone_number: str
    email: Optional[str]
    is_active: bool
    is_email_verified: bool
    trust_tier: TrustTier
    trust_score: int
    id_verified: bool
    skills: Optional[List[str]]
    zone: Optional[str]
    completions: int
    hours_served: float

    class Config:
        from_attributes = True

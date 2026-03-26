from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

router = APIRouter()

class PatchNote(BaseModel):
    version: str
    release_date: str
    title: str
    features: List[str]
    status: str
    note: Optional[str] = None

# Hardcoded patch data for now
PATCHES = [
    {
        "version": "1.5.0",
        "release_date": "2026-03-25",
        "title": "Trust & Track",
        "features": [
            "Multi-NGO Data Isolation",
            "JWT-based NGO Authentication",
            "Public Marketplace for Donation Alerts",
            "Atomic NGO Onboarding & Registration",
            "Telegram Bot Integration (Replacing Twilio/WhatsApp)",
            "Volunteer Trust Tiers (Unverified -> Field Verified)",
            "Automated Performance Stats (Completions/No-Shows)",
            "NGO Inventory Ledger"
        ],
        "status": "STABLE",
        "note": "Migration from Twilio to Telegram API for hackathon agility and free-tier access."
    },
    {
        "version": "1.0.0",
        "release_date": "2026-03-20",
        "title": "The Bridge (MVP)",
        "features": [
            "Legacy SMS/WhatsApp Dispatch (Twilio)",
            "Volunteer Activation Gate",
            "6-Digit OTP Security Engine (Brute-force protected)",
            "Need Management Dashboard"
        ],
        "status": "LEGACY"
    }
]

@router.get("/patches", response_model=List[PatchNote])
async def get_patch_notes():
    """
    Retrieve the history of system updates and version patches.
    """
    return PATCHES

@router.get("/version")
async def get_current_version():
    """
    Get the current active application version.
    """
    return {"version": "1.5.0", "codename": "Trust & Track"}

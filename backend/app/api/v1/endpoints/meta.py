from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
from backend.app.services.email_service import email_service

router = APIRouter()

class PatchNote(BaseModel):
    version: str
    release_date: str
    title: str
    features: List[str]
    status: str
    note: Optional[str] = None

class SMTPTestRequest(BaseModel):
    host: Optional[str] = None
    port: Optional[int] = None
    user: Optional[str] = None
    password: Optional[str] = None

# Hardcoded patch data for now
PATCHES = [
    {
        "version": "2.3.0",
        "release_date": "2026-04-08",
        "title": "SahyogSync Duality",
        "features": [
            "Dual-Engine Architecture (Marketplace & Campaigns)",
            "Web-Based Mission Briefing Flow",
            "Structured Volunteer Opt-in Gates",
            "PostGIS-enabled Spatial Matching",
            "Comprehensive Inventory (Strategic & Recovery)",
            "Bulletproof OTP Stabilization Fixes"
        ],
        "status": "STABLE",
        "note": "Complete architectural separation between reactive donor-recovery and proactive missions."
    },
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
        "status": "DEPRECATED",
        "note": "Migration from Twilio to Telegram API completed."
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
    return {"version": "2.0.0", "codename": "SahyogSync Duality"}

@router.post("/test-smtp")
async def test_smtp_diagnostic(data: Optional[SMTPTestRequest] = None):
    """
    Trigger a step-by-step diagnostic of the SMTP connection.
    Use this to identify where Render is blocking email traffic.
    """
    report = await email_service.diagnose_connection(
        host=data.host if data else None,
        port=data.port if data else None,
        user=data.user if data else None,
        password=data.password if data else None
    )
    return report

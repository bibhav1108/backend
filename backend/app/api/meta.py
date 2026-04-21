from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from backend.app.database import get_db
from backend.app.models import Organization, Volunteer, NGO_Campaign as Campaign, CampaignStatus

router = APIRouter()

class PatchNote(BaseModel):
    version: str
    release_date: str
    title: str
    features: List[str]
    status: str
    note: Optional[str] = None

class PublicStats(BaseModel):
    total_partners: int
    total_volunteers: int
    total_projects: int
    total_items: int
    recent_activity: List[dict]

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

import re

@router.get("/public/stats", response_model=PublicStats)
async def get_public_stats(db: AsyncSession = Depends(get_db)):
    """
    Publicly accessible global impact metrics.
    Jargon-free: NGOs -> Partners, Missions -> Projects.
    Adopted 'Inclusive Counting': Counts all registrations to reflect scale.
    """
    # 1. Total Partners (All Registered NGOs)
    org_stmt = select(func.count()).select_from(Organization)
    total_partners = (await db.execute(org_stmt)).scalar() or 0

    # 2. Total Volunteer Force (All Registrations)
    vol_stmt = select(func.count()).select_from(Volunteer)
    total_volunteers = (await db.execute(vol_stmt)).scalar() or 0

    # 3. Community Projects (All Statuses)
    camp_stmt = (
        select(Campaign)
        .options(selectinload(Campaign.organization))
    )
    all_projects = (await db.execute(camp_stmt)).scalars().all()
    
    total_projects = len(all_projects)
    total_items = 0
    
    recent_activity = []
    
    # Process project items and activity
    # Sort by created_at desc
    sorted_projects = sorted(all_projects, key=lambda x: x.created_at, reverse=True)
    
    # Helper to extract numbers from strings like "100kg" or "50 kits"
    def extract_qty(val: Any) -> float:
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str):
            # Find first number (integer or decimal) in string
            match = re.search(r"(\d+(\.\d+)?)", val)
            if match:
                return float(match.group(1))
        return 1.0 # Fallback

    for project in sorted_projects:
        # Sum up items
        if project.items:
            for qty_val in project.items.values():
                total_items += extract_qty(qty_val)
        
        # Add to activity feed (limit 5)
        if len(recent_activity) < 5:
            recent_activity.append({
                "id": project.id,
                "title": project.name,
                "org_name": project.organization.name if project.organization else "SahyogSync Partner",
                "status": "In Progress" if project.status == CampaignStatus.ACTIVE else ("Done" if project.status == CampaignStatus.COMPLETED else "Upcoming"),
                "completed_at": project.created_at.isoformat(),
                "impact": f"{len(project.items) if project.items else 0} resource types shared"
            })

    return {
        "total_partners": total_partners,
        "total_volunteers": total_volunteers,
        "total_projects": total_projects,
        "total_items": int(total_items),
        "recent_activity": recent_activity
    }

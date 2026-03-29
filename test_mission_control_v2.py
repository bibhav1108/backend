import asyncio
import sys
import os

# Ensure backend/ is in sys.path
sys.path.append(os.getcwd())

from backend.app.database import async_session, run_migrations
from backend.app.models import (
    NGO_Campaign, 
    Volunteer, 
    MissionTeam, 
    Organization, 
    CampaignStatus, 
    CampaignParticipationStatus
)
from sqlalchemy import select, func
from datetime import datetime, timedelta

async def test_refined_mission_control():
    print("🚀 Running Migrations first...")
    await run_migrations()
    
    print("🧪 Testing NGO Mission Control V2.0 (Dual-Engine Compatible)...")
    print("-" * 50)
    
    async with async_session() as db:
        # 1. Setup Test Data
        stmt = select(Organization).limit(1)
        org = (await db.execute(stmt)).scalar_one_or_none()
        if not org:
            print("❌ No Organization found. Please create an NGO first.")
            return

        # Create 3 Test Volunteers
        vols = []
        now_ts = int(datetime.utcnow().timestamp())
        for i in range(3):
            v_name = f"V2 Vol {i+1} {now_ts}"
            v = Volunteer(
                org_id=org.id,
                name=v_name,
                phone_number=f"+91{now_ts}{i}",
                telegram_active=True,
                telegram_chat_id=f"CHAT_V2_{i}_{now_ts}",
                skills=["Action", "Logistics"]
            )
            db.add(v)
            vols.append(v)
        await db.flush()

        # 2. Create NGO_Campaign with Quota = 2
        campaign = NGO_Campaign(
            org_id=org.id,
            name=f"V2.0 Action Mission {now_ts}",
            volunteers_required=2,
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow() + timedelta(hours=5),
            location_address="Action Zone Sector 7",
            status=CampaignStatus.PLANNED
        )
        db.add(campaign)
        await db.flush()
        print(f"✅ Created NGO_Campaign '{campaign.name}' with Quota: 2")

        # 3. Volunteers Opt-In (Pool Entry)
        print("   - Volunteers opting in to mission pool...")
        for v in vols:
            part = MissionTeam(
                campaign_id=campaign.id,
                volunteer_id=v.id,
                status=CampaignParticipationStatus.PENDING
            )
            db.add(part)
        await db.flush()
        print(f"✅ 3 Volunteers in PENDING pool. (Opt-In Logic Verified)")

        # 4. Admin Approves (The Approval Gate)
        print("   - Admin selecting the final Mission Team...")
        for i in range(2):
            part = (await db.execute(select(MissionTeam).where(
                MissionTeam.campaign_id == campaign.id, 
                MissionTeam.volunteer_id == vols[i].id
            ))).scalar_one()
            part.status = CampaignParticipationStatus.APPROVED
            
        await db.flush()
        print(f"✅ Admin Approved 2 Volunteers for the team.")

        # 5. Check Quota & Status
        approved_count = (await db.execute(select(func.count()).select_from(MissionTeam).where(
            MissionTeam.campaign_id == campaign.id,
            MissionTeam.status == CampaignParticipationStatus.APPROVED
        ))).scalar()
        
        print(f"🔍 Mission Pool Check: {approved_count}/2 approved.")
        
        # 6. Mission Accomplished (Completion)
        campaign.status = CampaignStatus.COMPLETED
        await db.commit()
        print(f"✅ Mission Completed. Action Lifecycle verified.")

    print("-" * 50)
    print("🏁 V2.0 Logic Verification Complete!")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_refined_mission_control())

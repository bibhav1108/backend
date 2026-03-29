from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from backend.app.config import settings

# Construct Async Database URL
if settings.DATABASE_URL:
    DATABASE_URL = settings.DATABASE_URL
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
    elif DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
else:
    DATABASE_URL = (
        f"postgresql+psycopg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )

# Create Async Engine
engine = create_async_engine(DATABASE_URL, echo=True)

# Create Sessionmaker
async_session = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Base class for models
class Base(DeclarativeBase):
    pass

from sqlalchemy import text
async def run_migrations():
    """V2.0 Core Re-Alignment: Renaming and Isolating Layers (High Performance)"""
    print("[Migrations] Starting Dual-Engine Schema Sync...")

    # 1. Pre-flight Check: Fetch all existing Enums and Types in ONE pass
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        
        # Get all existing Types
        existing_types = (await conn.execute(text("SELECT typname FROM pg_type WHERE typtype = 'e';"))).scalars().all()
        
        # Get all existing Enum Labels
        existing_labels = (await conn.execute(text("""
            SELECT t.typname, e.enumlabel 
            FROM pg_type t 
            JOIN pg_enum e ON t.oid = e.enumtypid;
        """))).all()
        labels_map = {}
        for row in existing_labels:
            labels_map.setdefault(row[0], set()).add(row[1])

        types_map = {
            'dispatchstatus': ['SENT', 'ACCEPTED', 'COMPLETED', 'FAILED'],
            'needstatus': ['OPEN', 'DISPATCHED', 'OTP_SENT', 'COMPLETED', 'CLOSED'],
            'campaignstatus': ['PLANNED', 'ACTIVE', 'COMPLETED'],
            'campaignparticipationstatus': ['PENDING', 'APPROVED', 'REJECTED'],
            'campaigntype': ['HEALTH', 'EDUCATION', 'BASIC_NEEDS', 'AWARENESS', 'EMERGENCY', 'ENVIRONMENT', 'SKILLS', 'OTHER'],
            'needtype': ['FOOD', 'WATER', 'KIT', 'BLANKET', 'MEDICAL', 'VEHICLE', 'OTHER'],
            'trusttier': ['UNVERIFIED', 'ID_VERIFIED', 'FIELD_VERIFIED'],
            'urgency': ['LOW', 'MEDIUM', 'HIGH']
        }
        
        for type_name, vals in types_map.items():
            if type_name not in existing_types:
                print(f"   - [INIT] Creating Type {type_name}...")
                await conn.execute(text(f"CREATE TYPE {type_name} AS ENUM ('{vals[0]}');"))
                current_labels = {vals[0]}
                vals = vals[1:]
            else:
                current_labels = labels_map.get(type_name, set())

            for val in vals:
                if val not in current_labels:
                    print(f"   - [UPDT] Adding '{val}' to {type_name}...")
                    try:
                        await conn.execute(text(f"ALTER TYPE {type_name} ADD VALUE '{val}';"))
                    except Exception as e:
                        print(f"     (Already exists or skipped: {e})")

    # 2. Table Renaming and Schema Updates
    async with engine.begin() as conn:
        print("[Migrations] Applying Table Renames & New Structures...")

        # Rename existing V1.0 tables to V2.0 Marketplace naming
        await conn.execute(text("ALTER TABLE IF EXISTS surplus_alerts RENAME TO marketplace_alerts;"))
        await conn.execute(text("ALTER TABLE IF EXISTS needs RENAME TO marketplace_needs;"))
        await conn.execute(text("ALTER TABLE IF EXISTS dispatches RENAME TO marketplace_dispatches;"))
        await conn.execute(text("ALTER TABLE IF EXISTS campaigns RENAME TO ngo_campaigns;"))
        await conn.execute(text("ALTER TABLE IF EXISTS campaign_participation RENAME TO mission_teams;"))

        # Marketplace Cleanup
        await conn.execute(text("ALTER TABLE IF EXISTS marketplace_needs RENAME COLUMN surplus_alert_id TO marketplace_alert_id;"))
        await conn.execute(text("ALTER TABLE IF EXISTS marketplace_dispatches RENAME COLUMN need_id TO marketplace_need_id;"))
        await conn.execute(text("ALTER TABLE IF EXISTS galleries RENAME COLUMN dispatch_id TO marketplace_dispatch_id;"))

        # Marketplace Alert Extensions
        await conn.execute(text("ALTER TABLE IF EXISTS marketplace_alerts ADD COLUMN IF NOT EXISTS is_confirmed BOOLEAN DEFAULT FALSE;"))
        await conn.execute(text("ALTER TABLE IF EXISTS marketplace_alerts ADD COLUMN IF NOT EXISTS is_processed BOOLEAN DEFAULT FALSE;"))

        # Create New Tables
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS marketplace_inventory (
                id SERIAL PRIMARY KEY,
                org_id INTEGER REFERENCES organizations(id),
                item_name VARCHAR NOT NULL,
                quantity FLOAT DEFAULT 0.0,
                unit VARCHAR NOT NULL,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))

        # Ensure Column Consistency for Volunteers (V1.5+)
        await conn.execute(text("ALTER TABLE volunteers ADD COLUMN IF NOT EXISTS telegram_chat_id VARCHAR;"))
        await conn.execute(text("ALTER TABLE volunteers ADD COLUMN IF NOT EXISTS telegram_active BOOLEAN DEFAULT FALSE;"))
        await conn.execute(text("ALTER TABLE volunteers ADD COLUMN IF NOT EXISTS trust_tier trusttier DEFAULT 'UNVERIFIED';"))
        await conn.execute(text("ALTER TABLE volunteers ADD COLUMN IF NOT EXISTS skills JSON;"))
        await conn.execute(text("ALTER TABLE volunteers ADD COLUMN IF NOT EXISTS location geometry(POINT, 4326);"))

        # Ensure Campaign Columns
        await conn.execute(text("ALTER TABLE IF EXISTS ngo_campaigns ADD COLUMN IF NOT EXISTS type campaigntype DEFAULT 'OTHER';"))
        await conn.execute(text("ALTER TABLE IF EXISTS ngo_campaigns ADD COLUMN IF NOT EXISTS start_time TIMESTAMP;"))
        await conn.execute(text("ALTER TABLE IF EXISTS ngo_campaigns ADD COLUMN IF NOT EXISTS end_time TIMESTAMP;"))
        await conn.execute(text("ALTER TABLE IF EXISTS ngo_campaigns ADD COLUMN IF NOT EXISTS volunteers_required INTEGER DEFAULT 0;"))
        await conn.execute(text("ALTER TABLE IF EXISTS ngo_campaigns ADD COLUMN IF NOT EXISTS location_address VARCHAR;"))

        # Final Cleanup: Remove references that cross-wire Marketplace and Campaign
        await conn.execute(text("ALTER TABLE marketplace_needs DROP COLUMN IF EXISTS campaign_id;"))
        await conn.execute(text("ALTER TABLE ngo_campaigns DROP COLUMN IF EXISTS target_quantity;")) # Cleanup legacy JSON mixing if any

    print("[Migrations] V2.0 Dual-Engine Sync Done.")

# Dependency to get AsyncSession 
async def get_db():
    async with async_session() as session:
        yield session
        await session.commit()

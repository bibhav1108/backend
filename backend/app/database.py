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

# Create Async Engine with production-ready connection pooling
engine = create_async_engine(
    DATABASE_URL, 
    echo=True,
    pool_pre_ping=True,  # Health check before using a connection
    pool_recycle=300,    # Retire connections older than 5 mins (Great for Neon/Serverless)
    pool_size=5,         # Base connection pool size
    max_overflow=10      # Allow up to 15 concurrent connections
)

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

    # 2. Table Renaming and Schema Updates (Idempotent)
    async with engine.begin() as conn:
        print("[Migrations] Applying Table Renames & New Structures...")

        # Safe Table Renames
        table_renames = [
            ("surplus_alerts", "marketplace_alerts"),
            ("needs", "marketplace_needs"),
            ("dispatches", "marketplace_dispatches"),
            ("campaigns", "ngo_campaigns"),
            ("campaign_participation", "mission_teams")
        ]
        
        for old_t, new_t in table_renames:
            await conn.execute(text(f"""
                DO $$ 
                BEGIN 
                    IF EXISTS (SELECT FROM pg_tables WHERE tablename = '{old_t}') AND 
                       NOT EXISTS (SELECT FROM pg_tables WHERE tablename = '{new_t}') THEN 
                        ALTER TABLE {old_t} RENAME TO {new_t}; 
                    END IF; 
                END $$;
            """))

        # Safe Column Renames
        column_renames = [
            ("marketplace_needs", "surplus_alert_id", "marketplace_alert_id"),
            ("marketplace_dispatches", "need_id", "marketplace_need_id"),
            ("galleries", "dispatch_id", "marketplace_dispatch_id")
        ]

        for table, old_c, new_c in column_renames:
            await conn.execute(text(f"""
                DO $$ 
                BEGIN 
                    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='{table}' AND column_name='{old_c}') AND
                       NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='{table}' AND column_name='{new_c}') THEN
                        ALTER TABLE {table} RENAME COLUMN {old_c} TO {new_c};
                    END IF;
                END $$;
            """))

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

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
            'urgency': ['LOW', 'MEDIUM', 'HIGH'],
            'notificationtype': ['DONOR_ALERT', 'MISSION_ACCEPTED', 'MISSION_COMPLETED', 'MISSION_CANCELLED', 'CAMPAIGN_INTEREST', 'SYSTEM'],
            'userrole': ['SYSTEM_ADMIN', 'NGO_COORDINATOR', 'VOLUNTEER'],
            'joinrequeststatus': ['PENDING', 'APPROVED', 'REJECTED'],
            'volunteerstatus': ['AVAILABLE', 'BUSY', 'ON_MISSION', 'INACTIVE'],
            'feedbacktype': ['REVIEW', 'ISSUE'],
            'ngotype': ['TRUST', 'SOCIETY', 'SECTION_8'],
            'ngoverificationstatus': ['DRAFT', 'VERIFICATION_REQUESTED', 'UNDER_REVIEW', 'APPROVED', 'REJECTED', 'VERIFIED_LIVE'],
            'adminidprooftype': ['AADHAAR', 'PAN', 'VOTER_ID', 'PASSPORT']
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

        # Marketplace Alert Extensions (Support V2.1 AI Structured Parser)
        await conn.execute(text("ALTER TABLE IF EXISTS marketplace_alerts ADD COLUMN IF NOT EXISTS item VARCHAR;"))
        await conn.execute(text("ALTER TABLE IF EXISTS marketplace_alerts ADD COLUMN IF NOT EXISTS quantity VARCHAR;"))
        await conn.execute(text("ALTER TABLE IF EXISTS marketplace_alerts ADD COLUMN IF NOT EXISTS location VARCHAR;"))
        await conn.execute(text("ALTER TABLE IF EXISTS marketplace_alerts ADD COLUMN IF NOT EXISTS notes TEXT;"))
        await conn.execute(text("ALTER TABLE IF EXISTS marketplace_alerts ADD COLUMN IF NOT EXISTS predicted_type needtype;"))
        await conn.execute(text("ALTER TABLE IF EXISTS marketplace_alerts ADD COLUMN IF NOT EXISTS predicted_urgency urgency;"))
        await conn.execute(text("ALTER TABLE IF EXISTS marketplace_alerts ADD COLUMN IF NOT EXISTS is_confirmed BOOLEAN DEFAULT FALSE;"))
        await conn.execute(text("ALTER TABLE IF EXISTS marketplace_alerts ADD COLUMN IF NOT EXISTS is_processed BOOLEAN DEFAULT FALSE;"))
        await conn.execute(text("ALTER TABLE IF EXISTS marketplace_alerts ADD COLUMN IF NOT EXISTS latitude FLOAT;"))
        await conn.execute(text("ALTER TABLE IF EXISTS marketplace_alerts ADD COLUMN IF NOT EXISTS longitude FLOAT;"))
        await conn.execute(text("ALTER TABLE IF EXISTS marketplace_needs ADD COLUMN IF NOT EXISTS latitude FLOAT;"))
        await conn.execute(text("ALTER TABLE IF EXISTS marketplace_needs ADD COLUMN IF NOT EXISTS longitude FLOAT;"))

        # Organization Extensions
        await conn.execute(text("ALTER TABLE IF EXISTS organizations ADD COLUMN IF NOT EXISTS about TEXT;"))
        await conn.execute(text("ALTER TABLE IF EXISTS organizations ADD COLUMN IF NOT EXISTS website_url VARCHAR;"))
        await conn.execute(text("ALTER TABLE IF EXISTS organizations ADD COLUMN IF NOT EXISTS logo_url VARCHAR;"))
        await conn.execute(text("ALTER TABLE IF EXISTS organizations ADD COLUMN IF NOT EXISTS ngo_type ngotype;"))
        await conn.execute(text("ALTER TABLE IF EXISTS organizations ADD COLUMN IF NOT EXISTS registration_number VARCHAR;"))
        await conn.execute(text("ALTER TABLE IF EXISTS organizations ADD COLUMN IF NOT EXISTS pan_number VARCHAR;"))
        await conn.execute(text("ALTER TABLE IF EXISTS organizations ADD COLUMN IF NOT EXISTS ngo_darpan_id VARCHAR;"))
        await conn.execute(text("ALTER TABLE IF EXISTS organizations ADD COLUMN IF NOT EXISTS office_address TEXT;"))
        await conn.execute(text("ALTER TABLE IF EXISTS organizations ADD COLUMN IF NOT EXISTS last_broadcast_at TIMESTAMP;"))
        await conn.execute(text("ALTER TABLE IF EXISTS organizations ADD COLUMN IF NOT EXISTS daily_broadcast_count INTEGER DEFAULT 0;"))
        
        # Update organizations status to use enum if it was varchar
        # This might be tricky if data exists, but since we are moving to Enums:
        await conn.execute(text("""
            DO $$ 
            BEGIN 
                IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='organizations' AND column_name='status' AND data_type='character varying') THEN
                    -- Map legacy strings to new ENUM values
                    UPDATE organizations SET status = 'APPROVED' WHERE status = 'active';
                    UPDATE organizations SET status = 'DRAFT' WHERE status = 'pending';
                    -- Cast to new type
                    ALTER TABLE organizations ALTER COLUMN status TYPE ngoverificationstatus USING status::ngoverificationstatus;
                    ALTER TABLE organizations ALTER COLUMN status SET DEFAULT 'DRAFT';
                END IF;
            END $$;
        """))

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

        # Volunteer Join Requests Table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS volunteer_join_requests (
                id SERIAL PRIMARY KEY,
                volunteer_id INTEGER NOT NULL REFERENCES volunteers(id),
                org_id INTEGER NOT NULL REFERENCES organizations(id),
                status joinrequeststatus DEFAULT 'PENDING',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))

        # Create Telegram Cleanup Log Table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS telegram_messages (
                id SERIAL PRIMARY KEY,
                chat_id VARCHAR NOT NULL,
                message_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS ix_telegram_messages_chat_id ON telegram_messages (chat_id);
        """))

        # Create Inbound Message Deduplication Table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS inbound_messages (
                id SERIAL PRIMARY KEY,
                chat_id VARCHAR NOT NULL,
                message_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT _chat_message_uc UNIQUE (chat_id, message_id)
            );
            CREATE INDEX IF NOT EXISTS ix_inbound_messages_chat_id ON inbound_messages (chat_id);
        """))

        # Create Audit Trail Table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_events (
                id SERIAL PRIMARY KEY,
                org_id INTEGER REFERENCES organizations(id),
                actor_id INTEGER,
                event_type VARCHAR NOT NULL,
                target_id VARCHAR,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))

        # Create Notifications Table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                org_id INTEGER REFERENCES organizations(id),
                type notificationtype NOT NULL,
                title VARCHAR NOT NULL,
                message TEXT NOT NULL,
                priority VARCHAR DEFAULT 'INFO',
                is_read BOOLEAN DEFAULT FALSE,
                data JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS ix_notifications_org_id ON notifications (org_id);
            CREATE INDEX IF NOT EXISTS ix_notifications_is_read ON notifications (is_read);
        """))

        # Create Platform Feedback Table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS platform_feedback (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                type feedbacktype NOT NULL,
                rating FLOAT,
                category VARCHAR,
                content TEXT NOT NULL,
                status VARCHAR DEFAULT 'PENDING',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))

        # Ensure Column Consistency for Volunteers (V1.5+)
        await conn.execute(text("ALTER TABLE volunteers ADD COLUMN IF NOT EXISTS telegram_chat_id VARCHAR;"))
        await conn.execute(text("ALTER TABLE volunteers ADD COLUMN IF NOT EXISTS telegram_active BOOLEAN DEFAULT FALSE;"))
        await conn.execute(text("ALTER TABLE volunteers ADD COLUMN IF NOT EXISTS trust_tier trusttier DEFAULT 'UNVERIFIED';"))
        await conn.execute(text("ALTER TABLE volunteers ADD COLUMN IF NOT EXISTS trust_score INTEGER DEFAULT 0;"))
        await conn.execute(text("ALTER TABLE volunteers ADD COLUMN IF NOT EXISTS id_verified BOOLEAN DEFAULT FALSE;"))
        await conn.execute(text("ALTER TABLE volunteers ADD COLUMN IF NOT EXISTS aadhaar_last_4 VARCHAR;"))
        await conn.execute(text("ALTER TABLE volunteers ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id);"))
        await conn.execute(text("ALTER TABLE volunteers ADD COLUMN IF NOT EXISTS skills JSON;"))
        await conn.execute(text("ALTER TABLE volunteers ADD COLUMN IF NOT EXISTS location geometry(POINT, 4326);"))
        await conn.execute(text("ALTER TABLE volunteers ADD COLUMN IF NOT EXISTS status volunteerstatus DEFAULT 'AVAILABLE';"))
        await conn.execute(text("ALTER TABLE volunteers ALTER COLUMN org_id DROP NOT NULL;"))

        # User Extension: Support Volunteers, Roles, and Email Verification
        await conn.execute(text("ALTER TABLE users ALTER COLUMN email DROP NOT NULL;"))
        await conn.execute(text("ALTER TABLE users ALTER COLUMN org_id DROP NOT NULL;"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR UNIQUE;"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS role userrole DEFAULT 'NGO_COORDINATOR';"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_email_verified BOOLEAN DEFAULT FALSE;"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_token VARCHAR;"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS unverified_email VARCHAR;"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_reset_otp VARCHAR;"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS otp_expires_at TIMESTAMP;"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_number VARCHAR;"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS id_proof_type adminidprooftype;"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS id_proof_number_encrypted VARCHAR;"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_image_url VARCHAR DEFAULT '/static/default_pfp.jpg';"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_verification_token ON users (verification_token);"))

        # Ensure Campaign Columns (Support V2.1 AI Architect and Detailed Mission Specs)
        await conn.execute(text("ALTER TABLE IF EXISTS ngo_campaigns ADD COLUMN IF NOT EXISTS type campaigntype DEFAULT 'OTHER';"))
        await conn.execute(text("ALTER TABLE IF EXISTS ngo_campaigns ADD COLUMN IF NOT EXISTS target_quantity VARCHAR;"))
        await conn.execute(text("ALTER TABLE IF EXISTS ngo_campaigns ADD COLUMN IF NOT EXISTS items JSON;"))
        await conn.execute(text("ALTER TABLE IF EXISTS ngo_campaigns ADD COLUMN IF NOT EXISTS start_time TIMESTAMP;"))
        await conn.execute(text("ALTER TABLE IF EXISTS ngo_campaigns ADD COLUMN IF NOT EXISTS end_time TIMESTAMP;"))
        await conn.execute(text("ALTER TABLE IF EXISTS ngo_campaigns ADD COLUMN IF NOT EXISTS volunteers_required INTEGER DEFAULT 0;"))
        await conn.execute(text("ALTER TABLE IF EXISTS ngo_campaigns ADD COLUMN IF NOT EXISTS required_skills JSON;"))
        await conn.execute(text("ALTER TABLE IF EXISTS ngo_campaigns ADD COLUMN IF NOT EXISTS location_address VARCHAR;"))

        # Create NGO Documents Table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ngo_documents (
                id SERIAL PRIMARY KEY,
                org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                document_type VARCHAR NOT NULL,
                document_url VARCHAR NOT NULL,
                is_mandatory BOOLEAN DEFAULT TRUE,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))

        # Final Cleanup: Remove references that cross-wire Marketplace and Campaign
        await conn.execute(text("ALTER TABLE marketplace_needs DROP COLUMN IF EXISTS campaign_id;"))

        # Registration Verifications Table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS registration_verifications (
                id SERIAL PRIMARY KEY,
                email VARCHAR NOT NULL UNIQUE,
                hashed_otp VARCHAR NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS ix_registration_verifications_email ON registration_verifications (email);
        """))
       
        # 3. Cascade Upgrade: Transition existing Foreign Keys to Logical Strategies
        print("[Migrations] Upgrading Foreign Keys to Logical Strategies...")
        
        # Ensure Nullability for SET NULL targets
        await conn.execute(text("ALTER TABLE mission_teams ALTER COLUMN volunteer_id DROP NOT NULL;"))
        await conn.execute(text("ALTER TABLE marketplace_dispatches ALTER COLUMN volunteer_id DROP NOT NULL;"))
        
        fk_query = """
            SELECT 
                tc.table_name, 
                kcu.column_name, 
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name,
                tc.constraint_name
            FROM 
                information_schema.table_constraints AS tc 
                JOIN information_schema.key_column_usage AS kcu
                  ON tc.constraint_name = kcu.constraint_name
                  AND tc.table_schema = kcu.table_schema
                JOIN (
                    SELECT constraint_name, table_name, column_name, table_schema
                    FROM information_schema.constraint_column_usage
                ) AS ccu
                  ON ccu.constraint_name = tc.constraint_name
                  AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public';
        """
        fks = (await conn.execute(text(fk_query))).all()
        
        # Define rule overrides (Default is CASCADE)
        special_rules = {
            ("mission_teams", "volunteer_id"): "SET NULL",
            ("marketplace_dispatches", "volunteer_id"): "SET NULL",
            ("volunteers", "org_id"): "SET NULL",
            ("users", "org_id"): "SET NULL",
            ("audit_events", "org_id"): "SET NULL"
        }

        for row in fks:
            table, col, f_table, f_col, con_name = row
            strategy = special_rules.get((table, col), "CASCADE")
            
            print(f"   - [FK] Updating {table}.{col} -> {f_table}.{f_col} ({strategy})")
            try:
                await conn.execute(text(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {con_name};"))
                await conn.execute(text(f"""
                    ALTER TABLE {table} 
                    ADD CONSTRAINT {con_name} 
                    FOREIGN KEY ({col}) REFERENCES {f_table}({f_col}) ON DELETE {strategy};
                """))
            except Exception as e:
                print(f"     (Skip Upgrade for {con_name}: {e})")

    print("[Migrations] V2.0 Dual-Engine Sync Done.")

# Dependency to get AsyncSession 
async def get_db():
    async with async_session() as session:
        yield session
        await session.commit()

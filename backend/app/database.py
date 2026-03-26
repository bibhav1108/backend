from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from backend.app.config import settings

# Construct Async Database URL
if settings.DATABASE_URL:
    DATABASE_URL = settings.DATABASE_URL
    # Ensure protocol is correct for SQLAlchemy + Psycopg 3
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
    """Manually add missing columns for V1.5 (SQLAlchemy create_all doesn't update schema)"""
    async with engine.begin() as conn:
        print("[Migrations] Checking for V1.5 columns...")
        # Volunteers
        await conn.execute(text("ALTER TABLE volunteers ADD COLUMN IF NOT EXISTS telegram_chat_id VARCHAR;"))
        await conn.execute(text("ALTER TABLE volunteers ADD COLUMN IF NOT EXISTS telegram_active BOOLEAN DEFAULT FALSE;"))
        await conn.execute(text("ALTER TABLE volunteers ADD COLUMN IF NOT EXISTS trust_tier VARCHAR DEFAULT 'UNVERIFIED';"))
        await conn.execute(text("ALTER TABLE volunteers ADD COLUMN IF NOT EXISTS skills JSON;"))
        await conn.execute(text("ALTER TABLE volunteers ADD COLUMN IF NOT EXISTS zone VARCHAR;"))
        await conn.execute(text("ALTER TABLE volunteers ADD COLUMN IF NOT EXISTS location geometry(POINT, 4326);"))
        
        # Stats
        await conn.execute(text("ALTER TABLE volunteer_stats ADD COLUMN IF NOT EXISTS hours_served FLOAT DEFAULT 0.0;"))
        
        # Dispatches
        await conn.execute(text("ALTER TABLE dispatches ADD COLUMN IF NOT EXISTS otp_hash VARCHAR;"))
        await conn.execute(text("ALTER TABLE dispatches ADD COLUMN IF NOT EXISTS otp_used BOOLEAN DEFAULT FALSE;"))
        await conn.execute(text("ALTER TABLE dispatches ADD COLUMN IF NOT EXISTS otp_expires_at TIMESTAMP;"))
        await conn.execute(text("ALTER TABLE dispatches ADD COLUMN IF NOT EXISTS otp_attempts INTEGER DEFAULT 0;"))
        
        # Organizations
        await conn.execute(text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'pending';"))
        
        # Needs
        await conn.execute(text("ALTER TABLE needs ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES organizations(id);"))
        await conn.execute(text("ALTER TABLE needs ADD COLUMN IF NOT EXISTS surplus_alert_id INTEGER REFERENCES surplus_alerts(id);"))
        
        print("[Migrations] Done.")

# Dependency to get AsyncSession in FastAPI routes
async def get_db():
    async with async_session() as session:
        yield session
        await session.commit()

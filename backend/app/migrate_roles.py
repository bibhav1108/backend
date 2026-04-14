import asyncio
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.database import async_session
from sqlalchemy import text

async def migrate_roles():
    async with async_session() as session:
        print("[Migration] Updating existing NGO_ADMIN users to NGO_COORDINATOR...")
        # Note: We use text() to avoid SQLAlchemy mapping issues if the enum is already changed in Python
        await session.execute(text("UPDATE users SET role = 'NGO_COORDINATOR' WHERE role = 'NGO_ADMIN'"))
        await session.commit()
        print("[Migration] Done.")

if __name__ == "__main__":
    asyncio.run(migrate_roles())

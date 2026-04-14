import asyncio
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.database import run_migrations

async def main():
    await run_migrations()
    print("Migrations completed successfully.")

if __name__ == "__main__":
    asyncio.run(main())

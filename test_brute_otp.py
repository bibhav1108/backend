import sys
import os
import hmac
import hashlib
from sqlalchemy import select

# Add parent directory to path so backend module is discoverable
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.database import async_session
from backend.app.models import Dispatch
from backend.app.config import settings

async def find_otp():
    import sys
    import asyncio
    
    async with async_session() as session:
        # Fetching latest dispatch to prove sequence
        stmt = select(Dispatch).order_by(Dispatch.id.desc()).limit(1)
        result = await session.execute(stmt)
        dispatch = result.scalar_one_or_none()
        if not dispatch or not dispatch.otp_hash:
             print("[Brute] No active dispatch or hash found.")
             return

        stored_hash = dispatch.otp_hash
        print(f"[Brute] Stored Hash: {stored_hash}")

        print("[Brute] Solving 6-digit hash target (000000 - 999999)...")
        for i in range(0, 1000000):
            code = f"{i:06d}"
            # Match the app/services/otp.py hash logic
            h = hmac.new(settings.SECRET_KEY.encode(), code.encode(), hashlib.sha256)
            current_hash = h.hexdigest()
            if hmac.compare_digest(current_hash, stored_hash):
                 print(f"[Brute] SUCCESS FOUND CODE: {code}")
                 print(f"CODE={code}")
                 return code

        
        print("[Brute] OTP Code not found in 6-digit range.")

if __name__ == "__main__":
    import asyncio
    # Windows loop fixer
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(find_otp())

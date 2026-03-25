import sys
import asyncio
import uvicorn
import os

# 1. ENFORCE WINDOWS ASYNCIO SELECTOR POLICY FIRST
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    print("[Launcher] Applied WindowsSelectorEventLoopPolicy")

# 2. RUN SERVER
if __name__ == "__main__":
    uvicorn.run(
        "backend.app.main:app", 
        host="0.0.0.0", 
        port=8005,  # Use 8005 to avoid port collisions
        reload=True  # Auto-reload for dev
    )

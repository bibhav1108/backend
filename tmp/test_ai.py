import asyncio
import os
import sys
import argparse
from dotenv import load_dotenv

# Load .env from backend directory
load_dotenv("backend/.env")

# Add the project root to sys.path to allow imports from backend
sys.path.append(os.getcwd())

from backend.app.services.ai_service import ai_service
from backend.app.config import settings

async def test_ai():
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", type=str, default="I have 10kg of Dal and Rice at Sector 62, Noida")
    args = parser.parse_args()
    
    print(f"Using API Key: {settings.GEMINI_API_KEY[:10]}...")
    print(f"Testing text: '{args.text}'")
    
    result = await ai_service.parse_surplus_text(args.text)
    print("\nResult:")
    print(result)

if __name__ == "__main__":
    asyncio.run(test_ai())

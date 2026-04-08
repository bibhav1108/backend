import asyncio
import os
import sys
import json
from dotenv import load_dotenv

# Add project root to sys.path
sys.path.append(r"d:\Sahyog Setu")

# Load environment
load_dotenv(r"d:\Sahyog Setu\backend\.env")

from backend.app.agents.campaign_agent import campaign_agent

async def test_campaign_agent():
    print("🚀 Testing AI Campaign Architect Agent (LangChain)...")
    prompt = "I want to feed 500 people in Gomti Nagar this Sunday morning. We need rice and dal."
    try:
        draft = await campaign_agent.generate_draft(prompt)
        print("\n🤖 AI GENERATED DRAFT:")
        print(json.dumps(draft, indent=2))
    except Exception as e:
        print(f"\n❌ FAILED: {e}")

if __name__ == "__main__":
    asyncio.run(test_campaign_agent())

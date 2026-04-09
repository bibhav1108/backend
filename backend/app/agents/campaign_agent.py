import json
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from backend.app.services.ai_service import ai_service
from backend.app.models import NeedType

class CampaignAgent:
    def __init__(self):
        self.model = ai_service.model
        self.parser = JsonOutputParser()
        
        # --- NGO Assistant Persona ---
        self.system_prompt = (
            "You are the SahyogSync AI NGO Campaign Assistant. "
            "Extract Goal, Scale, Location, and Timeline from coordinator notes.\n\n"
            "Identify what to take from the prompt and suggest missing values for: "
            "name, description, type, target_quantity, items, volunteers_required, "
            "required_skills, location_address, start_time, end_time.\n"
            "Today's date is {today}."
        )

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", self.system_prompt),
            ("human", "PROMPT: \"{text}\"")
        ])

        self.chain = self.prompt | self.model | self.parser

    async def generate_draft(self, text: str) -> Dict[str, Any]:
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            return await self.chain.ainvoke({"text": text, "today": today_str})
        except Exception:
            return {"name": "Campaign Draft", "description": text}

campaign_agent = CampaignAgent()

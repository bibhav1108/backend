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
            "You are the SahyogSync AI NGO Campaign Assistant.\n"
            "Extract campaign details from the input.\n\n"
            "Return ONLY valid JSON. No explanation, no extra text.\n\n"
            "JSON format:\n"
            "{{\n"
            '  "name": string,\n'
            '  "description": string,\n'
            '  "type": "ONE OF: HEALTH, EDUCATION, BASIC_NEEDS, AWARENESS, EMERGENCY, ENVIRONMENT, SKILLS, OTHER",\n'
            '  "target_quantity": number,\n'
            '  "items": {{ "item_name": number }},\n'
            '  "volunteers_required": number,\n'
            '  "required_skills": [string],\n'
            '  "location_address": string,\n'
            '  "start_time": string,\n'
            '  "end_time": string\n'
            "}}\n\n"
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
            # 1. Get raw response from model
            res = await self.model.ainvoke(
                self.prompt.format_messages(text=text, today=today_str)
            )
            raw_text = res.content
            
            # 2. Extract JSON (Handle potential Markdown fences)
            clean_json = raw_text
            if "```json" in raw_text:
                clean_json = raw_text.split("```json")[-1].split("```")[0].strip()
            elif "```" in raw_text:
                clean_json = raw_text.split("```")[-1].split("```")[0].strip()
            
            # 3. Parse and Return
            result = json.loads(clean_json)
            print("AI RESULT (Parsed):", result)
            return result

        except Exception as e:
            print("AI ERROR (Raw Output):", raw_text if 'raw_text' in locals() else "None")
            print("AI PARSE FAILED:", str(e))

            return {
                "name": "Campaign Draft",
                "description": text,
                "note": "Plan B: Manual Drafting Required (AI Parsing Failed)"
            }

campaign_agent = CampaignAgent()

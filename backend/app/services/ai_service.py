import os
import json
import re
from typing import Optional, Dict
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from backend.app.config import settings
import logging

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        if self.api_key:
            os.environ["GOOGLE_API_KEY"] = self.api_key
            self.model = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash",
                temperature=0,
                max_retries=2,
                request_timeout=20 # Fail fast to Plan B if API is slow
            )
            self.parser = JsonOutputParser()
            self.prompt = ChatPromptTemplate.from_messages([
                ("system", (
                    "You are a logistics assistant for Sahyog Setu, an NGO platform. "
                    "Extract donation details from the user's text into a strict JSON format. "
                    "\n\n### Fields to Extract:\n"
                    "- item: The specific item being donated (e.g., 'Rice', 'Blankets').\n"
                    "- quantity: The amount (e.g., '10kg', '5 packets').\n"
                    "- location: The pickup address or area mentioned.\n"
                    "- category: Must be one of [FOOD, WATER, KIT, BLANKET, MEDICAL, VEHICLE, OTHER].\n"
                    "- urgency: Must be one of [LOW, MEDIUM, HIGH]. Default to MEDIUM.\n"
                    "- notes: Any additional context (e.g., 'Expires tomorrow', 'Wait at gate').\n\n"
                    "### Examples:\n"
                    "1. Input: 'I have 10kg dal at Sector 62, Noida. It is quite fresh.'\n"
                    "   Output: {{\"item\": \"Dal\", \"quantity\": \"10kg\", \"location\": \"Sector 62, Noida\", \"category\": \"FOOD\", \"urgency\": \"MEDIUM\", \"notes\": \"Quite fresh\"}}\n\n"
                    "2. Input: 'URGENT: Need someone to pick up 5 medical kits immediately from Red Cross office.'\n"
                    "   Output: {{\"item\": \"Medical Kits\", \"quantity\": \"5\", \"location\": \"Red Cross office\", \"category\": \"MEDICAL\", \"urgency\": \"HIGH\", \"notes\": \"Immediate pickup requested\"}}\n\n"
                    "Return ONLY the JSON object. If a field is missing, use 'N/A'."
                )),
                ("human", "{text}")
            ])
            self.chain = self.prompt | self.model | self.parser
        else:
            self.model = None
            self.chain = None

    def _regex_fallback(self, text: str) -> Dict:
        """
        Plan B: Basic pattern matching if Gemini is exhausted.
        """
        # Simple extraction for " [Item] [Qty] "
        qty_match = re.search(r'(\d+\s*(?:kg|kg\.|packets|packets\.|ltr|litres|persons|units))', text, re.IGNORECASE)
        quantity = qty_match.group(1) if qty_match else "N/A"
        
        # Assume content before quantity is the item
        content = text.split(quantity)[0].strip() if qty_match else text[:30].strip()
        
        return {
            "item": content or "Donation Item",
            "quantity": quantity,
            "location": "See Text",
            "notes": "Plan B: AI Busy",
            "fallback_used": True
        }

    async def parse_surplus_text(self, text: str) -> Optional[Dict]:
        """
        Parse messy donor text. If Gemini fails/exhausts, use the Regex Fallback.
        """
        if not self.chain:
            return self._regex_fallback(text)

        try:
            # Attempt AI Parsing
            return await self.chain.ainvoke({"text": text})
        except Exception as e:
            # Detailed error logging for debugging
            logger.error(f"[AI ERROR] Gemini invocation failed: {str(e)}")
            return self._regex_fallback(text)

ai_service = AIService()

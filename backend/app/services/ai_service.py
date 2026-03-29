import os
import json
import re
from typing import Optional, Dict
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from backend.app.config import settings

class AIService:
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        if self.api_key:
            os.environ["GOOGLE_API_KEY"] = self.api_key
            self.model = ChatGoogleGenerativeAI(
                model="gemini-2.0-flash",
                temperature=0,
                max_retries=1 # Reduced for faster fallback
            )
            self.parser = JsonOutputParser()
            self.prompt = ChatPromptTemplate.from_messages([
                ("system", "Extract donation details from the user's message into JSON. Fields: item, quantity, location, notes. Return ONLY valid JSON."),
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
        qty_match = re.search(r'(\d+\s*(?:kg|kg\.|packets|packets\.|ltr|litres))', text, re.IGNORECASE)
        quantity = qty_match.group(1) if qty_match else "Unspecified Qty"
        
        # Assume first words before quantity or first 2 words are the item
        content = text.split(quantity)[0].strip() if qty_match else text[:20]
        
        return {
            "item": content or "Surplus Food",
            "quantity": quantity,
            "location": "See Raw Message",
            "notes": "AI Exhausted - Basic Sync Used",
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
            print(f"[AI EXHAUSTED] Falling back to manual pattern matching: {e}")
            return self._regex_fallback(text)

ai_service = AIService()

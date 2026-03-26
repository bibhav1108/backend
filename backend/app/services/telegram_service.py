import httpx
from backend.app.config import settings
from typing import Optional
import logging
import json

logger = logging.getLogger(__name__)

class TelegramService:
    def __init__(self):
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.api_url = f"https://api.telegram.org/bot{self.token}" if self.token else None

    async def send_message(self, chat_id: str, text: str, parse_mode: str = "Markdown", reply_markup: Optional[dict] = None) -> bool:
        """
        Send a message via Telegram Bot API with optional reply_markup.
        """
        if not self.api_url:
            logger.warning("[Telegram LOG] Bot Token missing. Mock message:")
            logger.info(f"[Telegram LOG] To: {chat_id} | Body: {text} | Markup: {reply_markup}")
            return True

        url = f"{self.api_url}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode
        }
        if reply_markup:
            if isinstance(reply_markup, dict):
                payload["reply_markup"] = json.dumps(reply_markup)
            else:
                payload["reply_markup"] = reply_markup

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json=payload)
                if response.status_code == 200:
                    return True
                logger.error(f"[Telegram ERROR] Failed to send message: {response.text}")
                return False
            except Exception as e:
                logger.error(f"[Telegram ERROR] Exception sending message: {e}")
                return False

telegram_service = TelegramService()

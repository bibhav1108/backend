import httpx
from backend.app.config import settings
from typing import Optional
import logging
import json
import os

logger = logging.getLogger(__name__)

class TelegramService:
    def __init__(self):
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.api_url = f"https://api.telegram.org/bot{self.token}" if self.token else None
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

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

        client = self._get_client()
        try:
            response = await client.post(url, json=payload)
            if response.status_code == 200:
                logger.info(f"[Telegram] Message sent to {chat_id}")
                return True
            logger.error(f"[Telegram ERROR] Failed to send message: {response.text}")
            return False
        except Exception as e:
            logger.error(f"[Telegram ERROR] Exception sending message: {e}")
            return False

    async def send_photo(self, chat_id: str, photo_path: str, caption: str = "", reply_markup: Optional[dict] = None) -> bool:
        """
        Send a photo to a chat with an optional caption and keyboard.
        """
        if not self.api_url:
            logger.warning("[Telegram LOG] Bot Token missing. Mock photo message:")
            logger.info(f"[Telegram LOG] To: {chat_id} | Photo: {photo_path} | Caption: {caption} | Markup: {reply_markup}")
            return True # Changed to True for mock success

        url = f"{self.api_url}/sendPhoto"
        
        # Determine if photo_path is a URL or a local file
        if photo_path.startswith("http"):
            payload = {
                "chat_id": chat_id,
                "photo": photo_path,
                "caption": caption,
                "parse_mode": "Markdown"
            }
            if reply_markup:
                payload["reply_markup"] = json.dumps(reply_markup) # Ensure reply_markup is dumped to JSON
                
            client = self._get_client()
            try:
                response = await client.post(url, json=payload)
                if response.status_code == 200:
                    logger.info(f"[Telegram] Photo sent to {chat_id} from URL: {photo_path}")
                    return True
                logger.error(f"[Telegram ERROR] Failed to send photo from URL: {response.text}")
                return False
            except Exception as e:
                logger.error(f"[Telegram ERROR] Exception sending photo from URL: {e}")
                return False
        else:
            # Handle local file upload
            if not os.path.exists(photo_path):
                logger.error(f"[Telegram ERROR] Local photo not found: {photo_path}")
                return False
                
            client = self._get_client()
            try:
                with open(photo_path, "rb") as f:
                    files = {"photo": f}
                    data = {
                        "chat_id": chat_id,
                        "caption": caption,
                        "parse_mode": "Markdown"
                    }
                    if reply_markup:
                        data["reply_markup"] = json.dumps(reply_markup)
                        
                    response = await client.post(url, data=data, files=files)
                    if response.status_code == 200:
                        logger.info(f"[Telegram] Photo sent to {chat_id} from local file: {photo_path}")
                        return True
                    logger.error(f"[Telegram ERROR] Failed to send local photo: {response.text}")
                    return False
            except Exception as e:
                logger.error(f"[Telegram ERROR] Exception sending local photo: {e}")
                return False

    async def set_bot_commands(self, chat_id: Optional[str] = None) -> bool:
        """
        Register bot commands. 
        If chat_id is provided, sets specific commands for that volunteer (Role-based).
        Otherwise, sets default public commands.
        """
        if not self.api_url:
            return False
            
        url = f"{self.api_url}/setMyCommands"
        
        public_commands = [
            {"command": "start", "description": "🚀 Main menu"},
            {"command": "donate", "description": "🎁 Report surplus food"},
            {"command": "about", "description": "ℹ️ About Sahyog Setu"},
            {"command": "help", "description": "🆘 Get assistance"},
            {"command": "tutorial", "description": "📖 How to use"}
        ]
        
        volunteer_commands = [
            {"command": "start", "description": "🚀 Main menu"},
            {"command": "leaderboard", "description": "🏆 Top volunteers"},
            {"command": "my_missions", "description": "👤 Profile & stats"},
            {"command": "cancel", "description": "⚠️ Cancel active mission"},
            {"command": "donate", "description": "🎁 Report surplus food"},
            {"command": "about", "description": "ℹ️ About Sahyog Setu"},
            {"command": "help", "description": "🆘 Get assistance"}
        ]
        
        payload = {
            "commands": volunteer_commands if chat_id else public_commands
        }
        
        if chat_id:
            payload["scope"] = {
                "type": "chat",
                "chat_id": chat_id
            }
        else:
            payload["scope"] = {"type": "default"}

        client = self._get_client()
        response = await client.post(url, json=payload)
        if response.status_code == 200:
            logger.info(f"[Telegram] Commands sync successful (chat_id={chat_id or 'default'}).")
            return True
        logger.error(f"[Telegram] Commands sync failed: {response.text}")
        return False

telegram_service = TelegramService()

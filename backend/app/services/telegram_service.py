import httpx
from backend.app.config import settings
from typing import Optional, List
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

    async def send_message(self, chat_id: str, text: str, parse_mode: str = "Markdown", reply_markup: Optional[dict] = None) -> Optional[int]:
        """
        Send a message via Telegram Bot API and return message_id.
        """
        if not self.api_url:
            logger.info(f"[Telegram MOCK] To: {chat_id} | Body: {text}")
            return 999

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
                data = response.json()
                msg_id = data.get("result", {}).get("message_id")
                return msg_id
            logger.error(f"[Telegram ERROR] Failed: {response.text}")
            return None
        except Exception as e:
            logger.error(f"[Telegram ERROR] Exception: {e}")
            return None

    async def send_photo(self, chat_id: str, photo_path: str, caption: str = "", reply_markup: Optional[dict] = None) -> Optional[int]:
        """
        Send a photo and return message_id if successful.
        """
        if not self.api_url:
            logger.info(f"[Telegram MOCK] Photo to {chat_id}")
            return 888

        url = f"{self.api_url}/sendPhoto"
        client = self._get_client()

        try:
            if photo_path.startswith("http"):
                payload = {"chat_id": chat_id, "photo": photo_path, "caption": caption, "parse_mode": "Markdown"}
                if reply_markup:
                    payload["reply_markup"] = json.dumps(reply_markup)
                response = await client.post(url, json=payload)
            else:
                if not os.path.exists(photo_path):
                    return None
                with open(photo_path, "rb") as f:
                    data = {"chat_id": chat_id, "caption": caption, "parse_mode": "Markdown"}
                    if reply_markup:
                        data["reply_markup"] = json.dumps(reply_markup)
                    response = await client.post(url, data=data, files={"photo": f})

            if response.status_code == 200:
                data = response.json()
                msg_id = data.get("result", {}).get("message_id")
                return msg_id
            return None
        except Exception as e:
            logger.error(f"[Telegram ERROR] Photo Exception: {e}")
            return None

    async def broadcast_photo(self, chat_ids: List[str], photo_url: str, caption: str) -> dict:
        """
        Broadcast a photo + caption to multiple chat IDs.
        Returns a summary of successes and failures.
        """
        results = {"success": 0, "failed": 0}
        for chat_id in chat_ids:
            msg_id = await self.send_photo(chat_id, photo_url, caption)
            if msg_id:
                results["success"] += 1
            else:
                results["failed"] += 1
        return results

    async def delete_message(self, chat_id: str, message_id: int) -> bool:
        """
        Delete a message from a chat.
        """
        if not self.api_url:
            return True
            
        url = f"{self.api_url}/deleteMessage"
        payload = {"chat_id": chat_id, "message_id": message_id}
        
        client = self._get_client()
        try:
            response = await client.post(url, json=payload)
            return response.status_code == 200
        except Exception:
            return False

    async def get_file_url(self, file_id: str) -> Optional[str]:
        """
        Get the download URL for a file from Telegram.
        """
        if not self.api_url:
            return None
            
        url = f"{self.api_url}/getFile"
        client = self._get_client()
        try:
            response = await client.post(url, json={"file_id": file_id})
            if response.status_code == 200:
                file_path = response.json().get("result", {}).get("file_path")
                if file_path:
                    token = settings.TELEGRAM_BOT_TOKEN
                    return f"https://api.telegram.org/file/bot{token}/{file_path}"
            return None
        except Exception:
            return None

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

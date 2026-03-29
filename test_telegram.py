import asyncio
import os
from backend.app.services.telegram_service import telegram_service
from backend.app.config import settings

async def test_start():
    # Attempt to send the welcome photo to a test chat ID
    # Use a known test chat ID or the user's if available
    chat_id = "6997763786" # From previous logs
    photo_url = "https://res.cloudinary.com/ddu9fvg8o/image/upload/v1740391443/Sahyog_Setu_Welcome_v2_fghj.png"
    text = "🤝 *Test Welcome Message*"
    
    print(f"Sending photo to {chat_id}...")
    msg_id = await telegram_service.send_photo(chat_id, photo_url, text)
    print(f"Result: {msg_id}")
    await telegram_service.close()

if __name__ == "__main__":
    asyncio.run(test_start())

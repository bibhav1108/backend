from twilio.rest import Client
from backend.app.config import settings
from typing import Optional

class TwilioService:
    def __init__(self):
        self.client = None
        if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN:
            self.client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        self.from_number = settings.TWILIO_WHATSAPP_NUMBER or "whatsapp:+14155238886"

    async def send_whatsapp_message(self, to_number: str, body: str) -> Optional[str]:
        """
        Send a WhatsApp message using Twilio API.
        to_number should include 'whatsapp:' prefix, e.g., 'whatsapp:+1234567890'
        """
        if not self.client:
            print("[Twilio LOG] Twilio Credentials missing, Mock message sent instead:")
            print(f"[Twilio LOG] To: {to_number} | Body: {repr(body)}")
            return "MOCK_MESSAGE_SID_SUCCESS"
            
        try:
            message = self.client.messages.create(
                from_=self.from_number,
                body=body,
                to=to_number
            )
            return message.sid
        except Exception as e:
            print(f"[Twilio ERROR] Failed to send whatsapp message: {e}")
            return None

twilio_service = TwilioService()

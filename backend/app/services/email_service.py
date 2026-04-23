import httpx
import traceback
from backend.app.config import settings
from backend.app.models import User


BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


class EmailService:
    @property
    def is_configured(self) -> bool:
        return bool(settings.BREVO_API_KEY)

    async def send_email(self, recipient_email: str, subject: str, html_content: str):
        """HTTP-based email sender via Brevo API."""
        if not self.is_configured:
            print("\n" + "="*50)
            print(f"📧 [MOCK EMAIL] To: {recipient_email}")
            print(f"📧 [MOCK EMAIL] Subject: {subject}")
            print(f"📧 [MOCK EMAIL] Content: {html_content}")
            print("="*50 + "\n")
            return

        from_email = settings.EMAILS_FROM_EMAIL or "sahyogsync.alerts@gmail.com"
        from_name = settings.EMAILS_FROM_NAME or "SahyogSync"

        payload = {
            "sender": {"name": from_name, "email": from_email},
            "to": [{"email": recipient_email}],
            "subject": subject,
            "htmlContent": html_content,
        }

        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "api-key": settings.BREVO_API_KEY,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(BREVO_API_URL, json=payload, headers=headers)

            if response.status_code == 201:
                data = response.json()
                print(f"[SUCCESS] Email sent via Brevo (MessageId: {data.get('messageId', 'N/A')}) to {recipient_email}")
            else:
                print(f"[ERROR] Brevo API failed ({response.status_code}): {response.text}")
        except Exception as e:
            print(f"[ERROR] Brevo API request failed: {e}")
            traceback.print_exc()

    async def send_verification_email(self, user: User, token: str):
        """Sends a verification link to the user's email."""
        verify_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
        
        subject = f"Verify your {settings.EMAILS_FROM_NAME} Account"
        html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <p>Hello,</p>
                <p>Thank you for registering with us.</p>
                <p>To complete your registration, please verify your email address by clicking the link below:</p>
                <p><a href="{verify_url}" style="color: #007bff; text-decoration: none;">{verify_url}</a></p>
                <p>This link will expire in 15 minutes for security reasons.</p>
                <p>If you did not create this account, please ignore this email.</p>
                <p>Best regards,<br>Team Support</p>
            </body>
        </html>
        """
        await self.send_email(user.email, subject, html)

    async def send_password_reset_otp(self, user: User, otp: str):
        """Sends a 6-digit OTP for password reset."""
        subject = f"Password Reset Code - {settings.EMAILS_FROM_NAME}"
        html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <p>Hello,</p>
                <p>We received a request to reset your password.</p>
                <p>Use the One-Time Password (OTP) below to proceed:</p>
                <p style="font-size: 18px; font-weight: bold;">🔐 OTP: {otp}</p>
                <p>This code is valid for the next 10 minutes.</p>
                <p>If you did not request a password reset, please ignore this email. Your account remains secure.</p>
                <p>Best regards,<br>Support Team</p>
            </body>
        </html>
        """
        await self.send_email(user.email, subject, html)

    async def send_email_update_otp(self, email: str, otp: str):
        """Sends a 6-digit OTP for updating email address."""
        subject = f"Email Verification Code - {settings.EMAILS_FROM_NAME}"
        html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <p>Hello,</p>
                <p>You requested to update your account email to this address.</p>
                <p>Use the One-Time Password (OTP) below to verify this email:</p>
                <p style="font-size: 18px; font-weight: bold;">🔐 OTP: {otp}</p>
                <p>This code is valid for the next 15 minutes.</p>
                <p>If you did not request this change, please ignore this email.</p>
                <p>Best regards,<br>Support Team</p>
            </body>
        </html>
        """
        await self.send_email(email, subject, html)

    async def send_registration_otp(self, email: str, otp: str):
        """Sends a 6-digit OTP for the new volunteer registration flow."""
        subject = f"Your Registration Code - {settings.EMAILS_FROM_NAME}"
        html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; text-align: center;">
                <div style="max-width: 600px; margin: auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
                    <h2 style="color: #007bff;">Welcome to Sahyog Sync!</h2>
                    <p>To verify your email address and join our volunteer network, please use the code below:</p>
                    <div style="font-size: 32px; font-weight: bold; letter-spacing: 5px; color: #333; margin: 30px 0; padding: 15px; background: #f8f9fa; border-radius: 5px; display: inline-block;">
                        {otp}
                    </div>
                    <p>This code will expire in 15 minutes.</p>
                    <p style="font-size: 12px; color: #777;">If you didn't request this, you can safely ignore this email.</p>
                </div>
            </body>
        </html>
        """
        await self.send_email(email, subject, html)

# Singleton instance
email_service = EmailService()

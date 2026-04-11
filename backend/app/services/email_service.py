import aiosmtplib
from email.message import EmailMessage
from backend.app.config import settings
from backend.app.models import User
import traceback

class EmailService:
    @property
    def is_configured(self) -> bool:
        return all([settings.SMTP_USER, settings.SMTP_PASSWORD, settings.EMAILS_FROM_EMAIL])

    async def send_email(self, recipient_email: str, subject: str, html_content: str):
        """Generic async email sender with fallback to logging."""
        if not self.is_configured:
            print("\n" + "="*50)
            print(f"📧 [MOCK EMAIL] To: {recipient_email}")
            print(f"📧 [MOCK EMAIL] Subject: {subject}")
            print(f"📧 [MOCK EMAIL] Content: {html_content}")
            print("="*50 + "\n")
            return

        message = EmailMessage()
        message["From"] = f"{settings.EMAILS_FROM_NAME} <{settings.EMAILS_FROM_EMAIL}>"
        message["To"] = recipient_email
        message["Subject"] = subject
        message.set_content(html_content, subtype="html")

        try:
            await aiosmtplib.send(
                message,
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USER,
                password=settings.SMTP_PASSWORD,
                use_tls=settings.SMTP_PORT == 465,
                start_tls=settings.SMTP_PORT == 587,
            )
            print(f"[SUCCESS] Email sent to {recipient_email}")
        except Exception as e:
            print(f"[ERROR] Failed to send email to {recipient_email}: {e}")
            traceback.print_exc()

    async def send_verification_email(self, user: User, token: str):
        """Sends a verification link to the user's email."""
        verify_url = f"{settings.BACKEND_URL}/api/v1/auth/verify-email?token={token}"
        
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

# Singleton instance
email_service = EmailService()

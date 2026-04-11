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
        # Verification link points back to the Backend API (which redirects to Frontend)
        verify_url = f"{settings.BACKEND_URL}/api/v1/auth/verify-email?token={token}"
        
        subject = f"Verify your {settings.EMAILS_FROM_NAME} Account"
        html = f"""
        <html>
            <body>
                <h2>Welcome to SahyogSync! 🌟</h2>
                <p>Hello {user.full_name or 'there'},</p>
                <p>Thank you for joining our mission. Please verify your email address to activate your account features and build trust in our network.</p>
                <div style="margin: 20px 0;">
                    <a href="{verify_url}" 
                       style="background-color: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
                       Verify Email Address
                    </a>
                </div>
                <p>If the button doesn't work, copy and paste this link into your browser:</p>
                <p>{verify_url}</p>
                <p>This link will expire in 24 hours.</p>
                <hr>
                <p>If you did not request this, please ignore this email.</p>
            </body>
        </html>
        """
        await self.send_email(user.email, subject, html)

    async def send_password_reset_otp(self, user: User, otp: str):
        """Sends a 6-digit OTP for password reset."""
        subject = f"Password Reset Code - {settings.EMAILS_FROM_NAME}"
        html = f"""
        <html>
            <body>
                <h2>Password Reset Request 🔐</h2>
                <p>Hello {user.full_name or 'there'},</p>
                <p>You requested a password reset. Use the following 6-digit code to set a new password:</p>
                <div style="font-size: 24px; font-weight: bold; padding: 10px; background-color: #f4f4f4; border-radius: 5px; display: inline-block;">
                    {otp}
                </div>
                <p>This code is valid for 10 minutes.</p>
                <p>If you did not request this, please change your security settings immediately.</p>
                <hr>
                <p>Safe volunteering!</p>
            </body>
        </html>
        """
        await self.send_email(user.email, subject, html)

# Singleton instance
email_service = EmailService()

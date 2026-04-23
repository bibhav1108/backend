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

    async def send_ngo_approval_email(self, email: str, org_name: str):
        """Notifies an NGO that their registration has been approved."""
        subject = f"Registration Approved: Welcome to {settings.EMAILS_FROM_NAME}!"
        html = f"""
        <html>
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333; background-color: #f9f9f9; padding: 40px;">
                <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 20px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.05); border: 1px solid #eef2f6;">
                    <div style="background: linear-gradient(135deg, #007bff 0%, #0056b3 100%); padding: 40px 20px; text-align: center; color: white;">
                        <h1 style="margin: 0; font-size: 28px; font-weight: 800; letter-spacing: -0.5px;">Congratulations! 🚀</h1>
                    </div>
                    <div style="padding: 40px;">
                        <p style="font-size: 18px; margin-top: 0;">Hello <strong>{org_name}</strong>,</p>
                        <p style="line-height: 1.8; font-size: 16px;">We are thrilled to inform you that your registration on <strong>{settings.EMAILS_FROM_NAME}</strong> has been reviewed and <strong>approved</strong> by our administrative team!</p>
                        <p style="line-height: 1.8; font-size: 16px;">Your organization is now live on the platform. You can now start creating campaigns, managing volunteers, and tracking your impact through your dashboard.</p>
                        <div style="text-align: center; margin: 40px 0;">
                            <a href="{settings.FRONTEND_URL}/login" style="background-color: #007bff; color: white; padding: 15px 35px; border-radius: 12px; text-decoration: none; font-weight: bold; font-size: 16px; display: inline-block; box-shadow: 0 4px 10px rgba(0,123,255,0.3);">Access Your Dashboard</a>
                        </div>
                        <p style="font-size: 14px; color: #666; font-style: italic;">Thank you for partnering with us to simplify social impact.</p>
                        <hr style="border: 0; border-top: 1px solid #eee; margin: 30px 0;">
                        <p style="font-size: 12px; color: #999; text-align: center; margin: 0;">
                            Best regards,<br>
                            <strong>The {settings.EMAILS_FROM_NAME} Team</strong>
                        </p>
                    </div>
                </div>
            </body>
        </html>
        """
        await self.send_email(email, subject, html)

    async def send_ngo_rejection_email(self, email: str, org_name: str):
        """Notifies an NGO that their registration has been rejected."""
        subject = f"Update regarding your registration - {settings.EMAILS_FROM_NAME}"
        html = f"""
        <html>
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333; background-color: #fff5f5; padding: 40px;">
                <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 20px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.05); border: 1px solid #fecaca;">
                    <div style="background: #ef4444; padding: 40px 20px; text-align: center; color: white;">
                        <h1 style="margin: 0; font-size: 24px; font-weight: 800;">Registration Status Update</h1>
                    </div>
                    <div style="padding: 40px;">
                        <p style="font-size: 18px; margin-top: 0;">Hello <strong>{org_name}</strong>,</p>
                        <p style="line-height: 1.8; font-size: 16px;">Thank you for your interest in joining <strong>{settings.EMAILS_FROM_NAME}</strong>. After carefully reviewing your application and documents, we are unable to approve your registration at this time.</p>
                        <div style="background-color: #fef2f2; border-left: 4px solid #ef4444; padding: 20px; margin: 25px 0; border-radius: 4px;">
                            <p style="margin: 0; font-size: 14px; color: #991b1b; font-weight: 600;">Reason: Information mismatch or insufficient documentation.</p>
                        </div>
                        <p style="line-height: 1.8; font-size: 16px;">You can log in to your account to review the errors or re-upload the necessary documents for a fresh review.</p>
                        <div style="text-align: center; margin: 40px 0;">
                            <a href="{settings.FRONTEND_URL}/login" style="background-color: #333; color: white; padding: 15px 35px; border-radius: 12px; text-decoration: none; font-weight: bold; font-size: 16px; display: inline-block;">Update Registration</a>
                        </div>
                        <hr style="border: 0; border-top: 1px solid #eee; margin: 30px 0;">
                        <p style="font-size: 12px; color: #999; text-align: center; margin: 0;">
                            Best regards,<br>
                            <strong>The {settings.EMAILS_FROM_NAME} Support Team</strong>
                        </p>
                    </div>
                </div>
            </body>
        </html>
        """
        await self.send_email(email, subject, html)

    async def send_admin_new_ngo_notification(self, org_name: str, org_email: str):
        """Notifies the System Admin that a new NGO has submitted for verification."""
        subject = f"🚨 New NGO Verification Request: {org_name}"
        html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; background-color: #f4f7f9; padding: 40px;">
                <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1); border: 1px solid #e1e8ed;">
                    <div style="background: #2c3e50; padding: 25px; text-align: center; color: white;">
                        <h2 style="margin: 0; font-size: 20px;">System Administrator Alert</h2>
                    </div>
                    <div style="padding: 30px;">
                        <p style="font-size: 16px; margin-top: 0;">A new organization has submitted details for <strong>verification</strong>.</p>
                        <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                            <p style="margin: 5px 0;"><strong>🏢 Organization:</strong> {org_name}</p>
                            <p style="margin: 5px 0;"><strong>📧 Contact Email:</strong> {org_email}</p>
                        </div>
                        <p style="font-size: 14px; color: #555;">Please log in to the administrative portal to review their documents and finalize the approval process.</p>
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="{settings.FRONTEND_URL}/admin/organizations" style="background: #007bff; color: white; padding: 12px 25px; border-radius: 8px; text-decoration: none; font-weight: bold; display: inline-block;">Review Application</a>
                        </div>
                        <p style="font-size: 12px; color: #999; text-align: center; margin-top: 40px; border-top: 1px solid #eee; padding-top: 20px;">
                            This is an automated system notification.
                        </p>
                    </div>
                </div>
            </body>
        </html>
        """
        await self.send_email(settings.ADMIN_EMAIL, subject, html)

# Singleton instance
email_service = EmailService()

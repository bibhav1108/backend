import aiosmtplib
from email.message import EmailMessage
from backend.app.config import settings
from backend.app.models import User
import traceback
import time
import socket
import ssl

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
            # Increase timeout for slow cloud environments like Render
            await aiosmtplib.send(
                message,
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USER,
                password=settings.SMTP_PASSWORD,
                use_tls=settings.SMTP_PORT == 465,
                start_tls=settings.SMTP_PORT == 587,
                timeout=30  # Increased timeout from default (usually 1.0 or 5.0)
            )
            print(f"[SUCCESS] Email sent to {recipient_email}")
        except aiosmtplib.errors.SMTPConnectTimeoutError:
            error_msg = (
                f"[ERROR] SMTP Connection Timeout on port {settings.SMTP_PORT}. "
                "HINT: If you are on Render/Cloud, port 587 is often blocked. "
                "Try switching SMTP_PORT to 465 in your enviroment variables."
            )
            print(error_msg)
        except Exception as e:
            print(f"[ERROR] Failed to send email to {recipient_email}: {e}")
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

    async def diagnose_connection(self):
        """
        Performs a step-by-step SMTP diagnostic to identify 
        where the connection is hanging or failing.
        """
        report = {
            "timestamp": time.time(),
            "config": {
                "host": settings.SMTP_HOST,
                "port": settings.SMTP_PORT,
                "user": settings.SMTP_USER,
                "use_tls": settings.SMTP_PORT == 465,
                "start_tls": settings.SMTP_PORT == 587,
            },
            "steps": [],
            "success": False,
            "error": None
        }

        def add_step(name, status, detail=None, duration=None):
            report["steps"].append({
                "name": name,
                "status": status,
                "detail": str(detail) if detail else None,
                "duration_ms": round(duration * 1000, 2) if duration else None
            })

        start_time = time.time()
        
        # Step 1: DNS Resolution
        try:
            dns_start = time.time()
            ip = socket.gethostbyname(settings.SMTP_HOST)
            add_step("DNS Resolution", "SUCCESS", f"Resolved to {ip}", time.time() - dns_start)
        except Exception as e:
            add_step("DNS Resolution", "FAILED", e)
            report["error"] = f"DNS Failed: {e}"
            return report

        # Step 2: Socket Connection (Connectivity Test)
        try:
            sock_start = time.time()
            s = socket.create_connection((settings.SMTP_HOST, settings.SMTP_PORT), timeout=10)
            s.close()
            add_step("Socket Connection", "SUCCESS", "Port reachable", time.time() - sock_start)
        except Exception as e:
            add_step("Socket Connection", "FAILED", e)
            report["error"] = f"Socket Failed: {e}. HINT: Render likely blocks port {settings.SMTP_PORT}"
            return report

        # Step 3: SMTP Handshake
        smtp = aiosmtplib.SMTP(
            hostname=settings.SMTP_HOST, 
            port=settings.SMTP_PORT, 
            use_tls=settings.SMTP_PORT == 465,
            timeout=15
        )
        
        try:
            handshake_start = time.time()
            await smtp.connect()
            add_step("SMTP Connect", "SUCCESS", "EHLO Received", time.time() - handshake_start)

            if settings.SMTP_PORT == 587:
                tls_start = time.time()
                await smtp.starttls()
                add_step("STARTTLS", "SUCCESS", "Encryption active", time.time() - tls_start)

            login_start = time.time()
            await smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            add_step("SMTP Login", "SUCCESS", f"Authenticated as {settings.SMTP_USER}", time.time() - login_start)
            
            report["success"] = True
        except Exception as e:
            add_step("SMTP Protocol", "FAILED", e)
            report["error"] = f"Protocol Error: {e}"
        finally:
            try:
                await smtp.quit()
            except:
                pass

        return report

# Singleton instance
email_service = EmailService()

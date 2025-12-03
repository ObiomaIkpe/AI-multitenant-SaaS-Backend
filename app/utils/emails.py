from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from pydantic import EmailStr
from app.config import settings

# Configure your email settings
mail_conf = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=settings.MAIL_PASSWORD,
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True
)

FRONTEND_URL = settings.FRONTEND_URL


async def send_otp_email(email: EmailStr, otp: str):
    """Send OTP via email"""
    html = f"""
    <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2>Password Reset OTP</h2>
            <p>Your OTP for password reset is:</p>
            <h1 style="color: #4CAF50; letter-spacing: 5px;">{otp}</h1>
            <p>This OTP will expire in <strong>15 minutes</strong>.</p>
            <p>If you didn't request this, please ignore this email.</p>
            <hr>
            <p style="color: #888; font-size: 12px;">This is an automated email, please do not reply.</p>
        </body>
    </html>
    """
    
    message = MessageSchema(
        subject="Password Reset OTP",
        recipients=[email],
        body=html,
        subtype="html"
    )
    
    fm = FastMail(mail_conf)
    await fm.send_message(message)


async def send_password_reset_email(email: str, token: str, name: str):
    reset_link = f"http://localhost:5173/reset-password?token={token}"
    
    html = f"""
    <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2>Hi {name},</h2>
            <p>You requested to reset your password.</p>
            <p>Click the link below to reset your password:</p>
            <a href="{reset_link}" style="background: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">Reset Password</a>
            <p>This link will expire in <strong>1 hour</strong>.</p>
            <p>If you didn't request this, please ignore this email.</p>
            <hr>
            <p style="color: #888; font-size: 12px;">This is an automated email, please do not reply.</p>
        </body>
    </html>
    """
    
    message = MessageSchema(
        subject="Password Reset Request",
        recipients=[email],
        body=html,
        subtype="html"
    )
    
    fm = FastMail(mail_conf)
    await fm.send_message(message)

# Send verification OTP email
async def send_verification_email(email: str, otp: str, name: str):
    html = f"""
    <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2>Hi {name},</h2>
            <p>Your email verification code is:</p>
            <h1 style="color: #4CAF50; letter-spacing: 5px;">{otp}</h1>
            <p>This code will expire in <strong>10 minutes</strong>.</p>
            <p>If you didn't request this, please ignore this email.</p>
            <hr>
            <p style="color: #888; font-size: 12px;">This is an automated email, please do not reply.</p>
        </body>
    </html>
    """
    
    message = MessageSchema(
        subject="Email Verification Code",
        recipients=[email],
        body=html,
        subtype="html"
    )
    
    fm = FastMail(mail_conf)
    await fm.send_message(message)

async def send_invitation_email(
    email: str,
    token: str,
    org_name: str,
    inviter_name: str
):
    """Send invitation email to new user."""
    
    setup_url = f"{FRONTEND_URL}/setup?token={token}"
    
    html = f"""
    <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2>Welcome to {org_name}!</h2>
            <p>Hi there,</p>
            <p><strong>{inviter_name}</strong> has invited you to join <strong>{org_name}</strong>.</p>
            <p>Click the button below to set up your account:</p>
            <a href="{setup_url}" style="background: #4CAF50; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 20px 0;">Complete Setup</a>
            <p>Or copy and paste this link in your browser:</p>
            <p style="word-break: break-all; color: #007bff;">{setup_url}</p>
            <p>This invitation will expire in <strong>7 days</strong>.</p>
            <hr>
            <p style="color: #888; font-size: 12px;">If you didn't expect this invitation, you can safely ignore this email.</p>
            <p style="color: #888; font-size: 12px;">This is an automated email, please do not reply.</p>
        </body>
    </html>
    """
    
    message = MessageSchema(
        subject=f"You've been invited to join {org_name}",
        recipients=[email],
        body=html,
        subtype="html"
    )
    
    fm = FastMail(mail_conf)
    await fm.send_message(message)
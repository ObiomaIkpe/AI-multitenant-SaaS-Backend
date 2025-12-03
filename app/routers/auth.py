from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
import random
from sqlalchemy.orm import Session
from datetime import timedelta, datetime, timezone
import secrets
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.models import User, EmailVerification, PasswordReset
from app.schemas.auth_schema import UserSignup, UserLogin, Token, ForgotPasswordRequest, ResetPasswordRequest, VerifyEmailRequest
from app.utils.auth import verify_password, get_password_hash, create_access_token
from app.config import settings
from app.utils.emails import *
from app.dependencies.dependencies_main import security
from app.dependencies.dependencies_main import get_current_user
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from pydantic import EmailStr

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Email Configuration
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

@router.post("/signup", status_code=201)
async def signUp(user_data: UserSignup, db: AsyncSession = Depends(get_db)):
    # Check if user exists
    stmt = select(User).where(User.email == user_data.email)
    result = await db.execute(stmt)
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists"
        )

    # Create user
    new_user = User(
        email=user_data.email,
        password_hash=get_password_hash(user_data.password),
        first_name=user_data.first_name,     
        last_name=user_data.last_name,
        status="active"
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return {"message": "User created successfully"}

@router.post("/login", response_model=Token)
async def login(credentials: UserLogin, db: AsyncSession = Depends(get_db)):
    stmt = select(User).where(User.email == credentials.email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    # if user.status != "active":
    #     raise HTTPException(
    #         status_code=status.HTTP_403_FORBIDDEN,
    #         detail="Account is not active"
    #     )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.user_id)},
        expires_delta=access_token_expires,
    )

    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=dict)
def get_current_user_info(current_user: User = Depends(get_current_user)):
    return {
        "user_id": current_user.user_id,
        "email": current_user.email,
        "org_id": current_user.org_id,
        "is_admin": current_user.is_admin
    }

# 1. FORGOT PASSWORD
@router.post("/forgot-password")
async def forgot_password(
    data: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(User).where(User.email == data.email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        return {"message": "Reset link has been sent"}
    
    # Generate token
    token = secrets.token_urlsafe(32)
    
    # Delete old reset tokens
    await db.execute(
        delete(PasswordReset).where(
            PasswordReset.user_id == user.user_id,
            PasswordReset.used == False
        )
    )
    
    # Create reset token
    reset = PasswordReset(
        user_id=user.user_id,
        token=token,
        expires_at=datetime.now() + timedelta(hours=1)
    )
    db.add(reset)
    await db.commit()
    
    # Send email in background
    background_tasks.add_task(
        send_password_reset_email,
        email=user.email,
        token=token,
        name=user.first_name
    )
    
    return {"message": "Reset link has been sent"}

# 2. RESET PASSWORD
@router.post("/reset-password")
async def reset_password(
    data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(PasswordReset).where(
        PasswordReset.token == data.token,
        PasswordReset.used == False,
        PasswordReset.expires_at > datetime.now(timezone.utc)
    )
    result = await db.execute(stmt)
    reset = result.scalar_one_or_none()
    
    if not reset:
        raise HTTPException(400, "Invalid or expired reset token")
    
    # Update password
    user_stmt = select(User).where(User.user_id == reset.user_id)
    user_result = await db.execute(user_stmt)
    user = user_result.scalar_one()
    
    user.password_hash = get_password_hash(data.new_password)
    reset.used = True
    
    await db.commit()
    
    return {"message": "Password reset successfully"}

# 3. SEND EMAIL VERIFICATION OTP
@router.post("/send-verification-otp")
async def send_verification_otp(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if current_user.email_verified:
        raise HTTPException(400, "Email already verified")
    
    # Generate 6-digit OTP
    otp = str(random.randint(100000, 999999))
    
    # Delete old OTPs
    await db.execute(
        delete(EmailVerification).where(
            EmailVerification.user_id == current_user.user_id,
            EmailVerification.verified == False
        )
    )
    
    # Create verification
    verification = EmailVerification(
        user_id=current_user.user_id,
        otp=otp,
        expires_at=datetime.now() + timedelta(minutes=10)
    )
    db.add(verification)
    await db.commit()
    
    # Send email
    background_tasks.add_task(
        send_verification_email,
        email=current_user.email,
        otp=otp,
        name=current_user.first_name
    )
    
    return {"message": "Verification code sent to email"}

# 4. VERIFY EMAIL WITH OTP
@router.post("/verify-email")
async def verify_email(
    data: VerifyEmailRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(EmailVerification).where(
        EmailVerification.user_id == current_user.user_id,
        EmailVerification.otp == data.otp,
        EmailVerification.verified == False,
        EmailVerification.expires_at > datetime.utcnow()
    )
    result = await db.execute(stmt)
    verification = result.scalar_one_or_none()
    
    if not verification:
        raise HTTPException(400, "Invalid or expired OTP")
    
    # Mark as verified
    current_user.email_verified = True
    verification.verified = True
    
    await db.commit()
    
    return {"message": "Email verified successfully"}



import random
import string
from datetime import datetime, timedelta
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def generate_otp(length: int = 6) -> str:
    """Generate a numeric OTP"""
    return ''.join(random.choices(string.digits, k=length))

def hash_otp(otp: str) -> str:
    """Hash OTP for secure storage"""
    return pwd_context.hash(otp)

def verify_otp(plain_otp: str, hashed_otp: str) -> bool:
    """Verify OTP against hash"""
    return pwd_context.verify(plain_otp, hashed_otp)

def get_otp_expiry(minutes: int = 15) -> datetime:
    """Get OTP expiry time"""
    return datetime.utcnow() + timedelta(minutes=minutes)

from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
from datetime import datetime
import uuid

# Invitation Schemas
class InviteUserRequest(BaseModel):
    email: EmailStr

class InviteUserResponse(BaseModel):
    invitation_id: uuid.UUID
    email: str
    expires_at: datetime
    message: str = "Invitation sent successfully"

# Setup Flow Schemas
class ValidateInviteRequest(BaseModel):
    token: str

class ValidateInviteResponse(BaseModel):
    valid: bool
    email: str
    org_name: str
    expires_at: datetime

class CompleteSetupRequest(BaseModel):
    token: str
    password: str = Field(..., min_length=8)
    first_name: str = Field(..., min_length=1, max_length=255)
    last_name: Optional[str] = Field(None, max_length=255)
    middle_name: Optional[str] = Field(None, max_length=255)

    @field_validator("password")
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        return v

class CompleteSetupResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    first_name: str
    org_id: uuid.UUID
    message: str = "Setup completed successfully. You can now log in."

from pydantic import BaseModel, EmailStr, HttpUrl, ConfigDict, StringConstraints
from typing import Optional, List, Annotated
from datetime import datetime
from uuid import UUID
from app.utils.enums import SubscriptionTier, SubscriptionStatus


class OrganizationCreate(BaseModel):
    org_name: str
    billing_email: EmailStr

    # Optional subscription info
    subscription_tier: Optional[SubscriptionTier] = None  # default handled in route
    subscription_status: Optional[str] = None  # optional, mostly for trial/free

    # Optional org settings
    max_users: Optional[int] = 20
    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    theme_color: Optional[str] = None
    domain: Optional[str] = None


class OrganizationResponse(BaseModel):
    org_id: UUID
    org_name: str
    subscription_status: str
    subscription_tier: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True

class OrganizationBrandingUpdate(BaseModel):
    org_name: Optional[str]
    logo_url: Optional[HttpUrl]
    favicon_url: Optional[HttpUrl]
    theme_color: Optional[Annotated[str, StringConstraints(pattern=r"^#(?:[0-9a-fA-F]{3}){1,2}$")]]
    domain: Optional[str]

    model_config = ConfigDict(from_attributes=True)

class OrganizationUpdate(BaseModel):
    org_name: Optional[str] = None
    billing_email: Optional[EmailStr] = None
    max_users: Optional[int] = None
    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    theme_color: Optional[str] = None
    domain: Optional[str] = None


class OrganizationResponseTesting(BaseModel):
    org_id: UUID
    org_name: str
    billing_email: EmailStr
    owner_user_id: UUID
    subscription_status: SubscriptionStatus
    subscription_tier: SubscriptionTier
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    billing_due_date: Optional[datetime] = None
    max_users: int
    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    theme_color: Optional[str] = None
    domain: Optional[str] = None
    created_at: datetime

    class Config:
        orm_mode = True  

class SubscriptionUpgrade(BaseModel):
    new_tier: SubscriptionTier

class TransferOwnership(BaseModel):
    new_owner_id: UUID
        
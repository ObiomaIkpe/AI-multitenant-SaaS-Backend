from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
from uuid import UUID


class UserBase(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str

class UserCreate(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    role_ids: List[UUID] = []


class UserResponse(BaseModel):
    user_id: UUID
    email: str
    tenant_id: UUID
    first_name: str
    last_name: str
    is_admin: bool
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

        
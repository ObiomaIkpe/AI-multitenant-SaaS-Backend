from pydantic import BaseModel, Field
from typing import Optional
from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime
from uuid import UUID

class RoleCreate(BaseModel):
    role_name: str
    description: Optional[str] = None

class RoleResponse(BaseModel):
    role_id: UUID
    role_name: str
    description: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)



class RoleUpdate(BaseModel):
    role_name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "role_name": "Executive Manager",
                "description": "Senior leadership role"
            }
        }
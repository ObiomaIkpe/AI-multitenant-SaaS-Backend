from pydantic import BaseModel
from datetime import datetime


# Pydantic Schemas
class ConversationCreate(BaseModel):
    title: str | None = None

class MessageCreate(BaseModel):
    content: str

class MessageResponse(BaseModel):
    message_id: UUID
    role: str
    content: str
    sources: str | None
    created_at: datetime

    class Config:
        from_attributes = True

class ConversationResponse(BaseModel):
    conversation_id: UUID
    title: str | None
    created_at: datetime
    last_message_at: datetime
    message_count: int = 0

    class Config:
        from_attributes = True



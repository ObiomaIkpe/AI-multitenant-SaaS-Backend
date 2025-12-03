from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
from app.database import get_db
from app.models import Conversation, Message, User
from app.dependencies.dependencies_main import get_current_user
from app.schemas.conversation_schema import ConversationCreate, ConversationResponse, MessageCreate, MessageResponse

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


# 1. Create new conversation
@router.post("/", response_model=ConversationResponse)
def create_conversation(
    data: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conversation = Conversation(
        user_id=current_user.user_id,
        org_id=current_user.org_id,
        title=data.title or "New Conversation"
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    
    return ConversationResponse(
        conversation_id=conversation.conversation_id,
        title=conversation.title,
        created_at=conversation.created_at,
        last_message_at=conversation.last_message_at,
        message_count=0
    )


# 2. List user's conversations
@router.get("/", response_model=List[ConversationResponse])
def list_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conversations = db.query(Conversation).filter(
        Conversation.user_id == current_user.user_id
    ).order_by(Conversation.last_message_at.desc()).all()
    
    return [
        ConversationResponse(
            conversation_id=c.conversation_id,
            title=c.title,
            created_at=c.created_at,
            last_message_at=c.last_message_at,
            message_count=len(c.messages)
        ) for c in conversations
    ]


# 3. Get conversation messages (with full context)
@router.get("/{conversation_id}/messages", response_model=List[MessageResponse])
def get_messages(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Verify ownership
    conversation = db.query(Conversation).filter(
        Conversation.conversation_id == conversation_id,
        Conversation.user_id == current_user.user_id
    ).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    messages = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.created_at.asc()).all()
    
    return messages


# 4. Send message (triggers agent workflow)
@router.post("/{conversation_id}/messages", response_model=MessageResponse)
async def send_message(
    conversation_id: UUID,
    data: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from app.agents.orchestrator import process_query
    
    # Verify conversation ownership
    conversation = db.query(Conversation).filter(
        Conversation.conversation_id == conversation_id,
        Conversation.user_id == current_user.user_id
    ).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Save user message
    user_message = Message(
        conversation_id=conversation_id,
        role="user",
        content=data.content
    )
    db.add(user_message)
    
    # Get conversation history for context
    previous_messages = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.created_at.asc()).all()
    
    context = [{"role": m.role, "content": m.content} for m in previous_messages]
    
    # Process query through agent pipeline
    result = await process_query(
        query=data.content,
        user_id=current_user.user_id,
        org_id=current_user.org_id,
        context=context,
        db=db
    )
    
    # Save assistant response
    assistant_message = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=result["answer"],
        sources=result.get("sources")  # JSON string of source docs
    )
    db.add(assistant_message)
    
    # Update conversation timestamp
    conversation.last_message_at = datetime.utcnow()
    
    db.commit()
    db.refresh(assistant_message)
    
    return assistant_message


# 5. Delete conversation
@router.delete("/{conversation_id}")
def delete_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conversation = db.query(Conversation).filter(
        Conversation.conversation_id == conversation_id,
        Conversation.user_id == current_user.user_id
    ).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    db.delete(conversation)
    db.commit()
    
    return {"message": "Conversation deleted"}
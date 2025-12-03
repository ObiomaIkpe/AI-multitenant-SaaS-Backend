from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional, List

class DocumentUploadResponse(BaseModel):
    doc_id: UUID  # Changed from document_id
    filename: str
    title: str  # Added
    status: str
    task_id: str  # Added - Celery task ID
    
    class Config:
        from_attributes = True


class DocumentResponse(BaseModel):
    doc_id: UUID  # Changed from document_id
    filename: str
    title: str
    author: Optional[str] = None
    tags: List[str] = []
    document_type: Optional[str] = None
    processing_status: str
    total_chunks: Optional[int] = None
    upload_date: datetime
    
    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    documents: List[DocumentResponse]
    total: int


class DocumentDetailResponse(BaseModel):
    doc_id: UUID
    title: str
    filename: str
    file_path: str
    author: Optional[str] = None
    tags: List[str] = []
    document_type: Optional[str] = None
    processing_status: str
    total_chunks: Optional[int] = None
    error_message: Optional[str] = None
    uploaded_by: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class Progress(BaseModel):
    percent: int
    step: str
    error: Optional[str] = None

class DocumentProgressResponse(BaseModel):
    doc_id: UUID
    status: str
    progress: Progress  # {percent: int, step: str, error: str}
    total_chunks: Optional[int] = None
    error: Optional[str] = None
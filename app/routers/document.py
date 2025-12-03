from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from typing import List, Optional
import os
import uuid
from datetime import datetime

from app.database import get_db
from app.models.models import Document, Organization, User
from app.schemas.document_schema import (
    DocumentUploadResponse,
    DocumentDetailResponse,
    DocumentProgressResponse,
    DocumentListResponse,
    DocumentResponse
)
from app.dependencies.dependencies_main import get_current_user, get_current_tenant
from app.tasks.document_tasks import process_document_pipeline, delete_document_vectors_task, retry_failed_document_task
from app.config import settings
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_progress_from_redis(document_id: str) -> dict:
    """Fetch processing progress from Redis"""
    import redis
    import json
    
    try:
        r = redis.Redis(
            host=getattr(settings, 'REDIS_HOST', 'localhost'),
            port=getattr(settings, 'REDIS_PORT', 6379),
            decode_responses=True
        )
        
        progress_key = f"progress:{document_id}"
        progress_data = r.get(progress_key)
        r.close()
        
        if progress_data:
            return json.loads(progress_data)
        return {"percent": 0, "step": "unknown", "error": None}
    
    except Exception as e:
        logger.error(f"Failed to fetch progress from Redis: {e}")
        return {"percent": 0, "step": "error", "error": str(e)}


def save_upload_file(tenant_id: str, file: UploadFile) -> tuple[str, str]:
    """
    Save uploaded file to disk with tenant isolation.
    
    Returns:
        tuple: (file_path, filename)
    """
    # Create tenant directory
    tenant_dir = os.path.join(settings.UPLOAD_DIR, tenant_id)
    os.makedirs(tenant_dir, exist_ok=True)
    
    # Generate unique filename
    file_ext = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(tenant_dir, unique_filename)
    
    # Save file
    with open(file_path, "wb") as buffer:
        buffer.write(file.file.read())
    
    return file_path, file.filename


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    title: Optional[str] = Query(None),
    author: Optional[str] = Query(None),
    tags: Optional[str] = Query(None),
    document_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Organization = Depends(get_current_tenant)
):
    """
    Upload a PDF document for processing.
    
    The document will be:
    1. Saved to disk with tenant isolation
    2. Recorded in database with metadata
    3. Queued for async processing (extract → chunk → embed → upsert)
    """
    try:
        # Validate file type
        if not file.filename.endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")
        
        # Extract tenant_id as string from Organization object
        tenant_id = str(tenant.org_id)
        
        # Save file
        file_path, original_filename = save_upload_file(tenant_id, file)
        
        # Create document record
        doc_id = str(uuid.uuid4())
        
        document = Document(
            doc_id=doc_id,
            tenant_id=tenant_id,
            title=title or original_filename,
            filename=original_filename,
            file_path=file_path,
            author=author,
            tags=tags.split(',') if tags else [],
            document_type=document_type,
            processing_status="pending",
            uploaded_by=current_user.user_id,
            created_at=datetime.utcnow()
        )
        
        db.add(document)
        await db.commit()
        await db.refresh(document)
        
        # ✅ FIXED: Queue processing pipeline using apply_async
        task_result = process_document_pipeline.apply_async(
            args=[tenant_id, doc_id, file_path]
        )
        
        logger.info(f"[Tenant: {tenant_id}] Document {doc_id} uploaded and queued with task_id: {task_result.id}")
        
        return DocumentUploadResponse(
            doc_id=doc_id,
            filename=original_filename,
            title=document.title,
            status="pending",
            task_id=task_result.id,
            message="Document uploaded successfully and queued for processing"
        )
    
    except Exception as e:
        logger.error(f"Upload failed: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/list", response_model=DocumentListResponse)
async def list_documents(
    skip: int = Query(0),
    limit: int = Query(20),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Organization = Depends(get_current_tenant)
):
    """
    List all documents for the current tenant with optional filtering.
    
    Query params:
    - skip: Pagination offset (default: 0)
    - limit: Max results (default: 20, max: 100)
    - status: Filter by processing_status (pending, processing, completed, failed)
    - search: Search in title, filename, author
    """
    try:
        tenant_id = str(tenant.org_id)
        
        # Build base query
        query = select(Document).where(Document.tenant_id == tenant_id)
        
        # Apply filters
        if status:
            query = query.where(Document.processing_status == status)
        
        if search:
            search_term = f"%{search}%"
            query = query.where(
                or_(
                    Document.title.ilike(search_term),
                    Document.filename.ilike(search_term),
                    Document.author.ilike(search_term)
                )
            )
        
        # Get total count
        count_query = select(func.count()).select_from(Document).where(Document.tenant_id == tenant_id)
        if status:
            count_query = count_query.where(Document.processing_status == status)
        if search:
            search_term = f"%{search}%"
            count_query = count_query.where(
                or_(
                    Document.title.ilike(search_term),
                    Document.filename.ilike(search_term),
                    Document.author.ilike(search_term)
                )
            )
        
        total_result = await db.execute(count_query)
        total = total_result.scalar()
        
        # Apply pagination
        limit = min(limit, 100)  # Cap at 100
        query = query.order_by(Document.created_at.desc()).offset(skip).limit(limit)
        
        result = await db.execute(query)
        documents = result.scalars().all()
        
        return DocumentListResponse(
            documents=documents,
            total=total,
            skip=skip,
            limit=limit
        )
    
    except Exception as e:
        logger.error(f"List documents failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{doc_id}", response_model=DocumentDetailResponse)
async def get_document(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Organization = Depends(get_current_tenant)
):
    """Get detailed information about a specific document."""
    try:
        tenant_id = str(tenant.org_id)
        
        result = await db.execute(
            select(Document).where(
                Document.doc_id == doc_id,
                Document.tenant_id == tenant_id
            )
        )
        document = result.scalar_one_or_none()
        
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        return DocumentDetailResponse(
            doc_id=document.doc_id,
            title=document.title,
            filename=document.filename,
            author=document.author,
            tags=document.tags,
            document_type=document.document_type,
            processing_status=document.processing_status,
            total_chunks=document.total_chunks,
            error_message=document.error_message,
            uploaded_by=document.uploaded_by,
            created_at=document.created_at,
            updated_at=document.updated_at,
            file_path=document.file_path
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get document failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{doc_id}/progress", response_model=DocumentProgressResponse)
async def get_processing_progress(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Organization = Depends(get_current_tenant)
):
    """
    Get real-time processing progress for a document.
    Progress is stored in Redis and updated by Celery workers.
    """
    try:
        tenant_id = str(tenant.org_id)

        # Verify document exists and belongs to tenant
        result = await db.execute(
            select(Document).where(
                Document.doc_id == doc_id,
                Document.tenant_id == tenant_id,
                Document.uploaded_by == current_user.user_id
            )
        )
        document = result.scalar_one_or_none()

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        # Get progress from Redis
        raw_progress = get_progress_from_redis(doc_id) or {}

        # Build a proper dictionary to match your Pydantic model
        progress_dict = {
            "percent": raw_progress.get("percent", 0),
            "step": raw_progress.get("step", "unknown"),
            "error": raw_progress.get("error")
        }

        return DocumentProgressResponse(
            doc_id=doc_id,
            status=document.processing_status,
            progress=progress_dict,
            total_chunks=document.total_chunks,
            error=raw_progress.get("error")
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get progress failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/{doc_id}/retry")
async def retry_failed_document(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Organization = Depends(get_current_tenant)
):
    """
    Retry processing a failed document.
    
    Only works for documents in 'failed' status.
    """
    try:
        tenant_id = str(tenant.org_id)
        
        result = await db.execute(
            select(Document).where(
                Document.doc_id == doc_id,
                Document.tenant_id == tenant_id
            )
        )
        document = result.scalar_one_or_none()
        
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        if document.processing_status != "failed":
            raise HTTPException(
                status_code=400,
                detail=f"Cannot retry document in '{document.processing_status}' status"
            )
        
        # Reset status and retry
        document.processing_status = "pending"
        document.error_message = None
        await db.commit()
        
        # ✅ FIXED: Queue retry task using apply_async
        task_result = retry_failed_document_task.apply_async(
            args=[tenant_id, doc_id]
        )
        
        return {
            "doc_id": doc_id,
            "status": "pending",
            "task_id": task_result.id,
            "message": "Document queued for retry"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Retry failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{doc_id}")
async def delete_document(
    doc_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Organization = Depends(get_current_tenant)
):
    """
    Delete a document and its associated vectors from Qdrant.
    
    This is a soft delete - the file remains on disk but the database record
    and all vectors are removed.
    """
    try:
        tenant_id = str(tenant.org_id)
        
        result = await db.execute(
            select(Document).where(
                Document.doc_id == doc_id,
                Document.tenant_id == tenant_id
            )
        )
        document = result.scalar_one_or_none()
        
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Delete vectors from Qdrant (background task)
        if document.processing_status == "completed":
            # ✅ FIXED: Use apply_async for background task
            delete_document_vectors_task.apply_async(
                args=[tenant_id, doc_id]
            )
        
        # Delete file from disk
        if os.path.exists(document.file_path):
            try:
                os.remove(document.file_path)
            except Exception as e:
                logger.warning(f"Failed to delete file {document.file_path}: {e}")
        
        # Delete from database
        await db.delete(document)
        await db.commit()
        
        logger.info(f"[Tenant: {tenant_id}] Deleted document {doc_id}")
        
        return {
            "doc_id": doc_id,
            "status": "deleted",
            "message": "Document and vectors deleted successfully"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete failed: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/summary")
async def get_document_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant: Organization = Depends(get_current_tenant)
):
    """
    Get summary statistics for documents in the current tenant.
    """
    try:
        tenant_id = str(tenant.org_id)
        
        # Total documents
        total_result = await db.execute(
            select(func.count()).select_from(Document).where(Document.tenant_id == tenant_id)
        )
        total = total_result.scalar()
        
        # Completed
        completed_result = await db.execute(
            select(func.count()).select_from(Document).where(
                Document.tenant_id == tenant_id,
                Document.processing_status == "completed"
            )
        )
        completed = completed_result.scalar()
        
        # Processing
        processing_result = await db.execute(
            select(func.count()).select_from(Document).where(
                Document.tenant_id == tenant_id,
                Document.processing_status.in_(["pending", "processing"])
            )
        )
        processing = processing_result.scalar()
        
        # Failed
        failed_result = await db.execute(
            select(func.count()).select_from(Document).where(
                Document.tenant_id == tenant_id,
                Document.processing_status == "failed"
            )
        )
        failed = failed_result.scalar()
        
        # Total chunks
        chunks_result = await db.execute(
            select(Document.total_chunks).where(
                Document.tenant_id == tenant_id,
                Document.processing_status == "completed"
            )
        )
        total_chunks = chunks_result.scalars().all()
        
        chunk_sum = sum([c for c in total_chunks if c is not None])
        
        return {
            "total_documents": total,
            "completed": completed,
            "processing": processing,
            "failed": failed,
            "total_chunks": chunk_sum,
            "success_rate": round((completed / total * 100) if total > 0 else 0, 2)
        }
    
    except Exception as e:
        logger.error(f"Stats failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
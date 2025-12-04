from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from typing import List, Optional
import os
import uuid


from app.config import settings
import logging

logger = logging.getLogger(__name__)


def normalize_tags(tags: List[str]) -> List[str]:
    """
    Normalize tags to prevent duplicates and maintain consistency.
    
    Rules:
    - Lowercase
    - Strip whitespace
    - Replace spaces with hyphens
    - Max 50 chars
    - Remove empty strings
    """
    if not tags:
        return []
    
    normalized = []
    for tag in tags:
        clean_tag = tag.lower().strip().replace(' ', '-')[:50]
        if clean_tag and clean_tag not in normalized:
            normalized.append(clean_tag)
    
    return normalized


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
    tenant_dir = os.path.join(settings.UPLOAD_DIR, tenant_id)
    os.makedirs(tenant_dir, exist_ok=True)
    
    file_ext = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(tenant_dir, unique_filename)
    
    with open(file_path, "wb") as buffer:
        buffer.write(file.file.read())
    
    return file_path, file.filename


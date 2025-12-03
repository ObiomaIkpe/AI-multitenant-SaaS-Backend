from PyPDF2 import PdfReader
from typing import List
import logging
import os
import asyncio
from pathlib import Path

logger = logging.getLogger(__name__)


def _extract_text_sync(file_path: str) -> str:
    """
    Synchronous PDF text extraction (runs in thread pool or Celery worker).
    This function performs blocking I/O and CPU-intensive operations.
    """
    try:
        reader = PdfReader(file_path)
        text = ""

        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        
        if len(text.strip()) < 100:
            logger.warning(f"Low text extraction from {file_path}, might need OCR")
            # TODO: Add OCR fallback with pytesseract

        return text
    except Exception as e:
        logger.error(f"Failed to extract text from {file_path}: {e}")
        raise


async def extract_text_from_pdf_async(file_path: str, tenant_id: str, max_size_mb: int = 100) -> str:
    """
    Async wrapper for PDF text extraction.
    Validates tenant access and runs extraction in thread pool.
    
    Security checks:
    - Validates file belongs to tenant
    - Checks file size limits
    - Validates file exists and is readable
    """
    # Security: Validate file path belongs to tenant
    tenant_upload_dir = Path(f"/uploads/{tenant_id}")
    file_path_obj = Path(file_path).resolve()
    
    if not str(file_path_obj).startswith(str(tenant_upload_dir.resolve())):
        logger.error(f"Unauthorized file access attempt: {file_path} by tenant {tenant_id}")
        raise PermissionError("Unauthorized file access")
    
    # Security: Validate file size
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    file_size = os.path.getsize(file_path)
    max_size_bytes = max_size_mb * 1024 * 1024
    if file_size > max_size_bytes:
        raise ValueError(f"File exceeds {max_size_mb}MB limit")
    
    # Run blocking PDF extraction in thread pool to avoid blocking event loop
    loop = asyncio.get_event_loop()
    text = await loop.run_in_executor(
        None,  # Uses default ThreadPoolExecutor
        _extract_text_sync,
        file_path
    )
    
    return text


def chunk_text_sync(text: str, chunk_size: int = 500, overlap: int = 100) -> List[str]:
    """
    Split text into overlapping chunks (synchronous version for Celery workers).
    
    Args:
        text: Input text to chunk
        chunk_size: Target size of each chunk in characters
        overlap: Number of characters to overlap between chunks (preserves context)
    """
    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = start + chunk_size

        # Don't break mid-word
        if end < text_length and text[end] != ' ':
            # Find last space before chunk_size
            last_space = text.rfind(' ', start, end)
            if last_space > start:
                end = last_space

        chunk = text[start:end].strip()
        if chunk:  # Only add non-empty chunks
            chunks.append(chunk)

        start = end - overlap  # Overlap for context preservation

    return chunks  # ✓ Fixed: outside the loop


async def chunk_text_async(text: str, chunk_size: int = 500, overlap: int = 100) -> List[str]:
    """
    Async version of chunk_text for use in FastAPI endpoints.
    Yields control to event loop for very large documents.
    """
    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = start + chunk_size

        if end < text_length and text[end] != ' ':
            last_space = text.rfind(' ', start, end)
            if last_space > start:
                end = last_space

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - overlap
        
        # Yield control every 100 chunks for large documents (prevents blocking)
        if len(chunks) % 100 == 0:
            await asyncio.sleep(0)

    return chunks
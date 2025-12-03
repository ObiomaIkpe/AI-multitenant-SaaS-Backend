import os
import json
import logging
from celery import chain
from PyPDF2 import PdfReader
from app.celery_app import celery_app
from app.database import SyncSessionLocal
from app.models.models import Document
from app.config import settings

# from app.api.embeddings_switch import generate_embeddings_batch
logger = logging.getLogger(__name__)

# =============================================================================
# REDIS HELPER FUNCTIONS
# =============================================================================

def get_redis_client():
    """Get Redis client for progress tracking."""
    import redis
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "redis"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        decode_responses=True
    )

def update_progress(document_id: str, percent: int, step: str, error: str = None):
    """Update task progress in Redis."""
    try:
        r = get_redis_client()
        r.setex(
            f"progress:{document_id}",
            3600,
            json.dumps({"percent": percent, "step": step, "error": error})
        )
        r.close()
    except Exception as e:
        logger.warning(f"Failed to update progress for {document_id}: {e}")

# =============================================================================
# DATABASE HELPER FUNCTION
# =============================================================================

def update_document_status(document_id: str, status: str, total_chunks: int = None, error_message: str = None):
    """Update document status in the database."""
    db = SyncSessionLocal()
    try:
        doc = db.query(Document).filter(Document.doc_id == document_id).first()
        if doc:
            doc.processing_status = status
            if total_chunks is not None:
                doc.total_chunks = total_chunks
            if error_message:
                doc.error_message = error_message
            db.commit()
    except Exception as e:
        logger.error(f"Failed to update document status for {document_id}: {e}")
        db.rollback()
    finally:
        db.close()

# =============================================================================
# TEXT CHUNKING HELPER
# =============================================================================

def chunk_with_smart_boundaries(text: str, chunk_size: int = 500, overlap: int = 75):
    """Chunk text with sentence and word boundary awareness."""
    chunks, start, text_length = [], 0, len(text)
    
    while start < text_length:
        end = start + chunk_size
        
        if end < text_length:
            # Prefer breaking at sentence
            sentence_end = max(
                text.rfind('. ', start, end),
                text.rfind('? ', start, end),
                text.rfind('! ', start, end)
            )
            if sentence_end > start + int(chunk_size * 0.7):
                end = sentence_end + 1
            else:
                space = text.rfind(' ', start, end)
                if space > start:
                    end = space
        
        chunk_text = text[start:end].strip()
        if len(chunk_text) > 50:
            chunks.append({"text": chunk_text, "char_start": start, "char_end": end})
        
        start = end - overlap
    
    return chunks

# =============================================================================
# PDF TEXT EXTRACTION WITH OCR
# =============================================================================

def extract_text_with_ocr_fallback(file_path: str, page_num: int, page_obj):
    """Extract text from PDF page; fallback to OCR for scanned pages."""
    text = page_obj.extract_text()
    if text and len(text.strip()) > 50:
        return {"page_number": page_num, "text": text, "method": "text_extraction"}
    
    # Likely scanned - use OCR
    logger.warning(f"Page {page_num} appears scanned, attempting OCR")
    
    try:
        import pytesseract
        from pdf2image import convert_from_path
        images = convert_from_path(file_path, first_page=page_num, last_page=page_num, dpi=300)
        if images:
            ocr_text = pytesseract.image_to_string(images[0], lang='eng', config='--psm 6')
            if len(ocr_text.strip()) > 10:
                return {"page_number": page_num, "text": ocr_text, "method": "ocr"}
    except ImportError:
        logger.error("OCR libraries not installed. Install: pip install pytesseract pdf2image")
    except Exception as e:
        logger.error(f"OCR failed for page {page_num}: {e}")
    
    return {"page_number": page_num, "text": "", "method": "failed"}

# =============================================================================
# CELERY TASKS
# =============================================================================

@celery_app.task(bind=True, name="document.extract_text", time_limit=600, soft_time_limit=540)
def extract_pdf_text_task(self, tenant_id: str, document_id: str, file_path: str):
    """Extract text from PDF page-by-page with OCR fallback."""
    try:
        logger.info(f"[Tenant={tenant_id}] [Doc={document_id}] [Task={self.request.id}] Starting text extraction")
        update_progress(document_id, 5, "starting")
        update_document_status(document_id, "processing")

        # Security validation
        expected_prefix = os.path.join(settings.UPLOAD_DIR, tenant_id)
        if not file_path.startswith(expected_prefix):
            raise PermissionError(f"Invalid file path for tenant {tenant_id}")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        update_progress(document_id, 10, "extracting_text")
        reader = PdfReader(file_path)
        total_pages = len(reader.pages)
        pages_data = []

        logger.info(f"[Tenant={tenant_id}] [Doc={document_id}] Processing {total_pages} pages")

        for i, page in enumerate(reader.pages, start=1):
            page_data = extract_text_with_ocr_fallback(file_path, i, page)
            if page_data["text"].strip():
                pages_data.append(page_data)
            progress = 10 + int((i / total_pages) * 15)
            update_progress(document_id, progress, f"extracted_page_{i}")

        if not pages_data:
            raise ValueError("No text could be extracted from PDF (all pages empty)")
        
        update_progress(document_id, 25, "text_extracted")
        
        total_chars = sum(len(p["text"]) for p in pages_data)
        logger.info(f"[Tenant={tenant_id}] [Doc={document_id}] Extracted {total_chars} characters from {len(pages_data)} pages")

        return {
            "tenant_id": tenant_id,
            "document_id": document_id,
            "pages": pages_data,
            "total_pages": len(pages_data),
            "total_chars": total_chars
        }

    except Exception as e:
        logger.error(f"[Tenant={tenant_id}] [Doc={document_id}] Text extraction failed: {e}", exc_info=True)
        update_progress(document_id, 0, "failed", error=str(e))
        update_document_status(document_id, "failed", error_message=str(e))
        raise

@celery_app.task(bind=True, name="document.chunk_text", time_limit=300, soft_time_limit=270)
def chunk_text_task(self, extraction_result: dict, chunk_size: int = 500, overlap: int = 75):
    """Chunk extracted text page-by-page with smart boundaries."""
    try:
        tenant_id = extraction_result["tenant_id"]
        document_id = extraction_result["document_id"]
        pages = extraction_result["pages"]
        
        logger.info(f"[Tenant={tenant_id}] [Doc={document_id}] [Task={self.request.id}] Starting chunking for {len(pages)} pages")
        update_progress(document_id, 30, "chunking_text")

        all_chunks = []
        global_index = 0
        
        for page_data in pages:
            page_chunks = chunk_with_smart_boundaries(page_data["text"], chunk_size, overlap)
            for idx, c in enumerate(page_chunks):
                all_chunks.append({
                    "text": c["text"],
                    "page_number": page_data["page_number"],
                    "chunk_index_in_page": idx,
                    "total_chunks_in_page": len(page_chunks),
                    "global_chunk_index": global_index,
                    "extraction_method": page_data["method"],
                    "char_start": c["char_start"],
                    "char_end": c["char_end"]
                })
                global_index += 1

        if not all_chunks:
            raise ValueError("No chunks generated from text")
        
        update_progress(document_id, 40, "storing_chunks")
        update_progress(document_id, 50, "chunks_stored")
        
        logger.info(f"[Tenant={tenant_id}] [Doc={document_id}] Created {len(all_chunks)} chunks across {len(pages)} pages")
        
        return {
            "tenant_id": tenant_id,
            "document_id": document_id,
            "chunks": all_chunks,
            "chunk_count": len(all_chunks),
            "page_count": len(pages)
        }

    except Exception as e:
        tenant_id = extraction_result.get("tenant_id", "unknown")
        document_id = extraction_result.get("document_id", "unknown")
        logger.error(f"[Tenant={tenant_id}] [Doc={document_id}] Chunking failed: {e}", exc_info=True)
        update_progress(document_id, 0, "failed", error=str(e))
        update_document_status(document_id, "failed", error_message=str(e))
        raise

@celery_app.task(bind=True, name="document.generate_embeddings", time_limit=1800, soft_time_limit=1700)
def generate_embeddings_task(self, chunk_result: dict):
    """Generate embeddings using Ollama for all chunks."""
    try:
        tenant_id = chunk_result["tenant_id"]
        document_id = chunk_result["document_id"]
        chunks = chunk_result["chunks"]
        
        logger.info(f"[Tenant={tenant_id}] [Doc={document_id}] [Task={self.request.id}] Generating embeddings for {len(chunks)} chunks")
        update_progress(document_id, 55, "generating_embeddings")

        # from app.services.embeddings import generate_embeddings_batch
        from app.api.embeddings_switch import generate_embeddings_batch
        texts = [c["text"] for c in chunks]
        embeddings = generate_embeddings_batch(texts)
        
        if len(embeddings) != len(chunks):
            raise ValueError(f"Embedding count mismatch: {len(embeddings)} != {len(chunks)}")

        update_progress(document_id, 75, "embeddings_generated")
        
        logger.info(f"[Tenant={tenant_id}] [Doc={document_id}] Generated {len(embeddings)} embeddings")
        
        return {
            "tenant_id": tenant_id,
            "document_id": document_id,
            "chunks": chunks,
            "embeddings": embeddings,
            "embedding_count": len(embeddings)
        }

    except Exception as e:
        tenant_id = chunk_result.get("tenant_id", "unknown")
        document_id = chunk_result.get("document_id", "unknown")
        logger.error(f"[Tenant={tenant_id}] [Doc={document_id}] Embedding generation failed: {e}", exc_info=True)
        update_progress(document_id, 0, "failed", error=str(e))
        update_document_status(document_id, "failed", error_message=str(e))
        raise

@celery_app.task(bind=True, name="document.upsert_vectors", time_limit=600, soft_time_limit=540)
def upsert_vectors_task(self, embedding_result: dict):
    """Upsert embeddings to Qdrant with complete metadata."""
    try:
        tenant_id = embedding_result["tenant_id"]
        document_id = embedding_result["document_id"]
        chunks = embedding_result["chunks"]
        embeddings = embedding_result["embeddings"]
        
        logger.info(f"[Tenant={tenant_id}] [Doc={document_id}] [Task={self.request.id}] Upserting {len(embeddings)} vectors to Qdrant")
        update_progress(document_id, 80, "upserting_vectors")

        # Get document metadata from database
        db = SyncSessionLocal()
        try:
            doc = db.query(Document).filter(Document.doc_id == document_id).first()
            if not doc:
                raise ValueError(f"Document {document_id} not found")
            
            metadata = {
                "title": doc.title,
                "filename": doc.filename,
                "author": getattr(doc, "author", None),
                "tags": getattr(doc, "tags", []),
                "document_type": getattr(doc, "document_type", None),
                "upload_date": getattr(doc, "created_at", None).isoformat() if getattr(doc, "created_at", None) else None,
                "uploaded_by": str(getattr(doc, "uploaded_by", None))
            }
        finally:
            db.close()

        from app.services.vector_store import upsert_to_qdrant_with_metadata
        collection_name = f"tenant_{tenant_id}"
        
        chunks_with_metadata = [
            {"embedding": e, "payload": {**c, **metadata}}
            for c, e in zip(chunks, embeddings)
        ]
        
        upsert_to_qdrant_with_metadata(collection_name, document_id, chunks_with_metadata, tenant_id)

        update_progress(document_id, 90, "vectors_upserted")
        update_document_status(document_id, "completed", total_chunks=len(chunks))
        update_progress(document_id, 100, "completed")
        
        logger.info(f"[Tenant={tenant_id}] [Doc={document_id}] Successfully processed - {len(embeddings)} vectors")
        
        return {
            "tenant_id": tenant_id,
            "document_id": document_id,
            "status": "completed",
            "vector_count": len(embeddings),
            "chunk_count": len(chunks)
        }

    except Exception as e:
        tenant_id = embedding_result.get("tenant_id", "unknown")
        document_id = embedding_result.get("document_id", "unknown")
        logger.error(f"[Tenant={tenant_id}] [Doc={document_id}] Upsert failed: {e}", exc_info=True)
        update_progress(document_id, 0, "failed", error=str(e))
        update_document_status(document_id, "failed", error_message=str(e))
        raise

# =============================================================================
# PIPELINE ORCHESTRATION
# =============================================================================

@celery_app.task(bind=True, name="document.process_pipeline")
def process_document_pipeline(self, tenant_id: str, document_id: str, file_path: str):
    """Orchestrate the complete document processing pipeline."""
    logger.info(f"[Tenant={tenant_id}] [Doc={document_id}] [Task={self.request.id}] Initiating processing pipeline")
    
    try:
        pipeline = chain(
            extract_pdf_text_task.s(tenant_id, document_id, file_path),
            chunk_text_task.s(),
            generate_embeddings_task.s(),
            upsert_vectors_task.s()
        )
        result = pipeline.apply_async()
        
        logger.info(f"[Tenant={tenant_id}] [Doc={document_id}] Pipeline queued with chain ID: {result.id}")
        
        return {
            "tenant_id": tenant_id,
            "document_id": document_id,
            "pipeline_task_id": result.id,
            "status": "queued"
        }
        
    except Exception as e:
        logger.error(f"[Tenant={tenant_id}] [Doc={document_id}] Failed to queue pipeline: {e}", exc_info=True)
        update_progress(document_id, 0, "failed", error=str(e))
        update_document_status(document_id, "failed", error_message=str(e))
        raise

# =============================================================================
# ADDITIONAL TASKS
# =============================================================================

@celery_app.task(bind=True, name="document.retry_failed")
def retry_failed_document_task(self, tenant_id: str, document_id: str):
    """Retry processing a failed document."""
    try:
        logger.info(f"[Tenant={tenant_id}] [Doc={document_id}] Retrying failed document")
        
        db = SyncSessionLocal()
        try:
            doc = db.query(Document).filter(
                Document.doc_id == document_id,
                Document.tenant_id == tenant_id
            ).first()
            
            if not doc:
                raise ValueError(f"Document {document_id} not found for tenant {tenant_id}")
            
            if doc.processing_status not in ["failed", "pending"]:
                raise ValueError(f"Document is not in failed state: {doc.processing_status}")
            
            file_path = doc.file_path
        finally:
            db.close()
        
        update_document_status(document_id, "pending")
        update_progress(document_id, 0, "retrying")
        
        task_result = process_document_pipeline.apply_async(
            args=[tenant_id, document_id, file_path]
        )
        
        return {
            "document_id": document_id,
            "new_task_id": task_result.id,
            "status": "queued"
        }
    
    except Exception as e:
        logger.error(f"[Tenant={tenant_id}] [Doc={document_id}] Failed to retry: {e}")
        raise

@celery_app.task(bind=True, name="document.delete_vectors")
def delete_document_vectors_task(self, tenant_id: str, document_id: str):
    """Delete document vectors from Qdrant when document is deleted."""
    try:
        logger.info(f"[Tenant={tenant_id}] [Doc={document_id}] Deleting vectors")
        
        from app.services.vector_store import delete_document_from_qdrant
        collection_name = f"tenant_{tenant_id}"
        delete_document_from_qdrant(collection_name, document_id)
        
        logger.info(f"[Tenant={tenant_id}] [Doc={document_id}] Successfully deleted vectors")
        
        return {
            "tenant_id": tenant_id,
            "document_id": document_id,
            "status": "deleted"
        }
    
    except Exception as e:
        logger.error(f"[Tenant={tenant_id}] [Doc={document_id}] Failed to delete vectors: {e}")
        raise
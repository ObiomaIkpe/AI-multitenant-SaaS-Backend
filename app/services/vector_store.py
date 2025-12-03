from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from typing import List, Dict, Any
from app.config import settings
import uuid
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

def get_qdrant_client() -> QdrantClient:
    """Get Qdrant client instance"""
    
    host = getattr(settings, 'QDRANT_HOST', 'localhost')
    port = getattr(settings, 'QDRANT_PORT', 6333)
    api_key = getattr(settings, 'QDRANT_API_KEY', None)
    
    if api_key:
        client = QdrantClient(url=f"https://{host}", api_key=api_key)
    else:
        client = QdrantClient(host=host, port=port)
    
    return client


def ensure_collection_exists(collection_name: str, vector_size: int = 768):
    """Ensure collection exists, create if not"""
    
    client = get_qdrant_client()
    
    try:
        collections = client.get_collections().collections
        collection_names = [col.name for col in collections]
        
        if collection_name not in collection_names:
            logger.info(f"Creating collection: {collection_name}")
            
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=Distance.COSINE
                )
            )
            
            logger.info(f"Collection {collection_name} created")
    
    except Exception as e:
        logger.error(f"Failed to ensure collection exists: {e}")
        raise


def upsert_to_qdrant_with_metadata(
    collection_name: str,
    document_id: str,
    chunks_with_metadata: List[Dict[str, Any]],
    tenant_id: str
):
    """Upsert vectors with full metadata to Qdrant"""
    
    logger.info(f"Upserting {len(chunks_with_metadata)} vectors to {collection_name}")
    
    client = get_qdrant_client()
    
    # Get vector size from first embedding
    vector_size = len(chunks_with_metadata[0]["embedding"]) if chunks_with_metadata else 768
    ensure_collection_exists(collection_name, vector_size)
    
    # Prepare points
    points = []
    
    for chunk_data in chunks_with_metadata:
        point_id = str(uuid.uuid4())
        
        payload = {
            "tenant_id": tenant_id,
            "document_id": document_id,
            **chunk_data["payload"]  # All metadata
        }
        
        point = PointStruct(
            id=point_id,
            vector=chunk_data["embedding"],
            payload=payload
        )
        
        points.append(point)
    
    # Upsert in batches
    batch_size = 100
    
    for i in range(0, len(points), batch_size):
        batch = points[i:i + batch_size]
        
        client.upsert(
            collection_name=collection_name,
            points=batch,
            wait=True
        )
        
        logger.debug(f"Upserted batch {i//batch_size + 1}")
    
    logger.info(f"Successfully upserted {len(points)} vectors")


def delete_document_from_qdrant(collection_name: str, document_id: str):
    """Delete all vectors for a document"""
    
    client = get_qdrant_client()
    
    logger.info(f"Deleting document {document_id} from {collection_name}")
    
    try:
        client.delete(
            collection_name=collection_name,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=document_id)
                    )
                ]
            ),
            wait=True
        )
        
        logger.info(f"Deleted document {document_id}")
    
    except Exception as e:
        logger.error(f"Failed to delete document: {e}")
        raise
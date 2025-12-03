from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from app.config import settings

client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)

def init_qdrant():
    """Create collection if it doesn't exist"""
    collections = client.get_collections().collections
    collection_names = [c.name for c in collections]

    if "documents" not in collection_names:
        client.create_collection(
            collection_name="documents",
            vectors_config=VectorParams(
                size=384,
                distance=Distance.COSINE
            )
        )
        print("✅ Created 'documents' collection in Qdrant")
    else:
        print("✅ 'documents' collection already exists")

init_qdrant()
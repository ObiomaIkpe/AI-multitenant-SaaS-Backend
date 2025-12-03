# app/api/local_embeddings.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from sentence_transformers import SentenceTransformer
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["embeddings"])

MODEL_NAME = "all-MiniLM-L6-v2"
model = SentenceTransformer(MODEL_NAME)
logger.info(f"Model {MODEL_NAME} loaded successfully")


class EmbedRequest(BaseModel):
    texts: List[str]


class QueryRequest(BaseModel):
    query: str


class EmbedResponse(BaseModel):
    embeddings: List[List[float]]
    count: int


class QueryResponse(BaseModel):
    embedding: List[float]


@router.post("/embed", response_model=EmbedResponse)
async def embed(request: EmbedRequest):
    try:
        if not request.texts:
            raise HTTPException(status_code=400, detail="No texts provided")
        
        embeddings = model.encode(
            request.texts,
            show_progress_bar=False,
            convert_to_numpy=True
        )
        
        return {
            "embeddings": embeddings.tolist(),
            "count": len(embeddings)
        }
    except Exception as e:
        logger.error(f"Embedding error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/embed/query", response_model=QueryResponse)
async def embed_query(request: QueryRequest):
    try:
        if not request.query:
            raise HTTPException(status_code=400, detail="No query provided")
        
        embedding = model.encode(request.query, convert_to_numpy=True)
        
        return {"embedding": embedding.tolist()}
    except Exception as e:
        logger.error(f"Query embedding error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "model": MODEL_NAME,
        "dimension": model.get_sentence_embedding_dimension()
    }
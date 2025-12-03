# app/services/embeddings.py

import requests
from typing import List
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

OLLAMA_URL = "http://localhost:11434"


def generate_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """Generate embeddings using Ollama (self-hosted)"""
    
    logger.info(f"Generating embeddings for {len(texts)} texts using Ollama")
    
    embeddings = []
    
    for idx, text in enumerate(texts):
        try:
            response = requests.post(
                f"{OLLAMA_URL}/api/embeddings",
                json={
                    "model": "nomic-embed-text",
                    "prompt": text
                },
                timeout=30
            )
            
            if response.status_code == 200:
                embedding = response.json()['embedding']
                embeddings.append(embedding)
            else:
                raise Exception(f"Ollama API error: {response.status_code}")
            
            # Log progress every 50 chunks
            if (idx + 1) % 50 == 0:
                logger.info(f"Processed {idx + 1}/{len(texts)} embeddings")
                
        except Exception as e:
            logger.error(f"Failed to generate embedding for chunk {idx}: {e}")
            raise
    
    logger.info(f"Generated {len(embeddings)} embeddings successfully")
    return embeddings


def generate_query_embedding(query: str) -> List[float]:
    """Generate embedding for search queries"""
    
    response = requests.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={
            "model": "nomic-embed-text",
            "prompt": query
        },
        timeout=30
    )
    
    if response.status_code != 200:
        raise Exception(f"Ollama API error: {response.status_code}")
    
    return response.json()['embedding']
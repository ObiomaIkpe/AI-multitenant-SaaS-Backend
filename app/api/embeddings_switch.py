import logging
from typing import List
import requests

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Determine which embedding service to use
USE_OLLAMA = bool(settings.USE_OLLAMA)
OLLAMA_URL = settings.OLLAMA_URL
LOCAL_EMBEDDING_SERVICE = "http://host.docker.internal:8000/local/embeddings"

def generate_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """
    Generate embeddings for a list of texts.
    Uses Ollama in production (container), or local sentence-transformers service in dev.
    """
    if USE_OLLAMA:
        # Production: Use Ollama
        embeddings = []
        logger.info(f"[Ollama] Generating embeddings for {len(texts)} texts")
        for idx, text in enumerate(texts):
            try:
                response = requests.post(
                    f"{OLLAMA_URL}/api/embeddings",
                    json={"model": "nomic-embed-text", "prompt": text},
                    timeout=30
                )
                if response.status_code == 200:
                    embedding = response.json()['embedding']
                    embeddings.append(embedding)
                else:
                    raise Exception(f"Ollama API error: {response.status_code} - {response.text}")

                if (idx + 1) % 50 == 0:
                    logger.info(f"[Ollama] Processed {idx + 1}/{len(texts)} embeddings")
            except Exception as e:
                logger.error(f"Failed to generate embedding for chunk {idx}: {e}")
                raise
        return embeddings
    
    else:
        # Dev: Use local sentence-transformers service
        logger.info(f"[LocalService] Generating embeddings for {len(texts)} texts")
        try:
            response = requests.post(
                f"{LOCAL_EMBEDDING_SERVICE}/embed",
                json={"texts": texts},
                timeout=120
            )
            if response.status_code == 200:
                data = response.json()
                return data['embeddings']
            else:
                raise Exception(f"Local embedding service error: {response.status_code} - {response.text}")
        except requests.exceptions.ConnectionError:
            raise Exception(
                f"Cannot connect to local embedding service at {LOCAL_EMBEDDING_SERVICE}. "
                "Make sure to run: python local_embeddings.py"
            )
        except Exception as e:
            logger.error(f"Local embedding service failed: {e}")
            raise


def generate_query_embedding(query: str) -> List[float]:
    """Generate embedding for a single query."""
    if USE_OLLAMA:
        response = requests.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": "nomic-embed-text", "prompt": query},
            timeout=30
        )
        if response.status_code != 200:
            raise Exception(f"Ollama API error: {response.status_code} - {response.text}")
        return response.json()['embedding']
    
    else:
        # Use local service
        try:
            response = requests.post(
                f"{LOCAL_EMBEDDING_SERVICE}/embed/query",
                json={"query": query},
                timeout=30
            )
            if response.status_code == 200:
                return response.json()['embedding']
            else:
                raise Exception(f"Local embedding service error: {response.status_code}")
        except Exception as e:
            logger.error(f"Local embedding service failed: {e}")
            raise
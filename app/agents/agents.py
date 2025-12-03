from typing import List, Dict
from uuid import UUID
from sqlalchemy.orm import Session
import json

from app.models import User, UserRole
from app.qdrant_client import qdrant_client
# from app.llm import get_embedding, generate_answer

MOCK_MODE = True  # Set to False when you deploy with real LLM


async def process_query(
    query: str,
    user_id: UUID,
    org_id: UUID,
    context: List[Dict],
    db: Session
) -> Dict:
    """
    Main orchestrator for the 4-agent pipeline with conversation context
    """
    
    # Get user's roles for filtering
    user_roles = db.query(UserRole).filter(UserRole.user_id == user_id).all()
    role_ids = [str(ur.role_id) for ur in user_roles]
    
    # Agent 1: Query Intelligence
    enhanced_query = await agent_1_query_intelligence(query, context)
    
    # Agent 2: Qdrant Retrieval with tenant + role filters
    chunks = await agent_2_retrieve_chunks(
        query=enhanced_query,
        tenant_id=str(org_id),
        role_ids=role_ids
    )
    
    # Agent 3: Chunk Validation
    validated_chunks = await agent_3_validate_chunks(enhanced_query, chunks)
    
    # Agent 4: Answer Generation with context
    answer, sources = await agent_4_generate_answer(
        query=query,
        chunks=validated_chunks,
        context=context
    )
    
    return {
        "answer": answer,
        "sources": json.dumps(sources)
    }


async def agent_1_query_intelligence(query: str, context: List[Dict]) -> str:
    """
    Agent 1: Enhances query with conversation context
    """
    if MOCK_MODE:
        # In mock mode, just return the query
        return query
    
    # Build context summary
    context_text = "\n".join([
        f"{msg['role']}: {msg['content']}" 
        for msg in context[-6:]  # Last 3 exchanges
    ])
    
    prompt = f"""Given this conversation history:
{context_text}

Latest question: {query}

Rephrase the question to be standalone and clear. Include relevant context from history if needed.

Standalone question:"""
    
    enhanced = await generate_answer(prompt, max_tokens=100)
    return enhanced.strip()


async def agent_2_retrieve_chunks(
    query: str,
    tenant_id: str,
    role_ids: List[str],
    limit: int = 10
) -> List[Dict]:
    """
    Agent 2: Retrieve chunks from Qdrant with tenant + role filtering
    """
    if MOCK_MODE:
        # Return mock chunks for testing
        return [
            {
                "text": f"Mock chunk {i} related to: {query}",
                "doc_id": f"doc-{i}",
                "score": 0.9 - (i * 0.05)
            }
            for i in range(5)
        ]
    
    # Get query embedding
    query_vector = await get_embedding(query)
    
    # Search with filters
    results = qdrant_client.search(
        collection_name="documents",
        query_vector=query_vector,
        query_filter={
            "must": [
                {"key": "tenant_id", "match": {"value": tenant_id}},
                {"key": "allowed_role_ids", "match": {"any": role_ids}}
            ]
        },
        limit=limit,
        with_payload=True
    )
    
    return [
        {
            "text": hit.payload["text"],
            "doc_id": hit.payload["doc_id"],
            "chunk_index": hit.payload.get("chunk_index", 0),
            "score": hit.score
        }
        for hit in results
    ]


async def agent_3_validate_chunks(query: str, chunks: List[Dict]) -> List[Dict]:
    """
    Agent 3: Score and filter chunks by relevance
    """
    if MOCK_MODE:
        # Simple filtering in mock mode
        return [c for c in chunks if c["score"] > 0.7]
    
    # In real mode, you could use LLM to score relevance
    # For now, just use vector similarity score
    threshold = 0.75
    return [c for c in chunks if c["score"] >= threshold]


async def agent_4_generate_answer(
    query: str,
    chunks: List[Dict],
    context: List[Dict]
) -> tuple[str, List[Dict]]:
    """
    Agent 4: Generate final answer with conversation context
    """
    if MOCK_MODE:
        # Mock response
        sources = [{"doc_id": c["doc_id"], "chunk": c["chunk_index"]} for c in chunks[:3]]
        return (
            f"Mock answer for: {query}\n\nBased on {len(chunks)} retrieved chunks.",
            sources
        )
    
    # Build context from chunks
    context_text = "\n\n".join([
        f"[Source {i+1}]: {chunk['text']}"
        for i, chunk in enumerate(chunks[:5])
    ])
    
    # Build conversation history (last 4 exchanges)
    history_text = "\n".join([
        f"{msg['role'].title()}: {msg['content']}"
        for msg in context[-8:]  # Last 4 exchanges
    ])
    
    prompt = f"""You are a helpful AI assistant. Answer based on the provided context and conversation history.

Conversation History:
{history_text}

Context from documents:
{context_text}

Current Question: {query}

Instructions:
- Answer based primarily on the context
- Reference conversation history when relevant
- If context doesn't contain the answer, say so
- Be concise and direct

Answer:"""
    
    answer = await generate_answer(prompt, max_tokens=500)
    
    sources = [
        {"doc_id": chunk["doc_id"], "chunk_index": chunk["chunk_index"]}
        for chunk in chunks[:5]
    ]
    
    return answer.strip(), sources
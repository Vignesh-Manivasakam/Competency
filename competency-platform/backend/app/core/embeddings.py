# app/core/embeddings.py
"""RAG Pipeline — pgvector content retrieval and embedding.

From spec §18.1 Listing 20:
Used by Content Generator Agent and Competency Architect Agent
to ground LLM outputs in validated organisational knowledge.
"""
from langchain_openai import OpenAIEmbeddings
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy import text
from app.core.config import settings

embeddings_model = OpenAIEmbeddings(
    model=settings.OPENAI_EMBEDDING_MODEL,  # text-embedding-3-small
    dimensions=settings.EMBEDDING_DIMENSIONS,  # 1536
    openai_api_key=settings.OPENAI_API_KEY or "mock-key",
)


async def embed_content(content: str) -> list[float]:
    """Generate embedding vector for content text."""
    return await embeddings_model.aembed_query(content)


async def retrieve_similar_content(
    session: AsyncSession,
    query: str,
    skill_id: str,
    content_type: str,
    top_k: int = 3,
    min_quality: float = 0.82,
) -> list[dict]:
    """Retrieve similar validated content from pgvector.
    
    Uses cosine distance (<=> operator) for similarity search.
    Only returns content with quality_score >= min_quality threshold.
    """
    query_vec = await embed_content(query)
    result = await session.execute(text("""
        SELECT id, content_body, quality_score, difficulty_level,
               1 - (embedding <=> CAST(:qv AS vector)) AS similarity
        FROM content_items
        WHERE skill_id = :sid
          AND content_type = :ctype
          AND quality_score >= :mq
          AND embedding IS NOT NULL
        ORDER BY embedding <=> CAST(:qv AS vector)
        LIMIT :tk
    """), {"qv": str(query_vec), "sid": skill_id,
           "ctype": content_type, "mq": min_quality, "tk": top_k})
    
    # Cosine similarity in pgvector: 1 - cosine_distance. Ordered by <=> ascending
    # since cosine distance of 0 means identical vectors, ordering by distance <=> is ascending.
    return [dict(row) for row in result.mappings()]


async def embed_and_store(
    session: AsyncSession,
    content_item_id: str,
    content_text: str,
):
    """Generate and store embedding for a content item."""
    embedding = await embed_content(content_text)
    await session.execute(text("""
        UPDATE content_items SET embedding = CAST(:emb AS vector)
        WHERE id = :cid
    """), {"emb": str(embedding), "cid": content_item_id})
    await session.commit()

from typing import List

import google.generativeai as genai

from app.config import settings

genai.configure(api_key=settings.GEMINI_API_KEY)


def embed_texts(texts: List[str], task_type: str = "retrieval_document") -> List[List[float]]:
    """
    Generate embeddings for a list of texts using the Gemini embedding model.

    Args:
        texts: List of strings to embed.
        task_type: "retrieval_document" for indexing, "retrieval_query" for queries.

    Returns:
        List of embedding vectors (each a list of floats).
    """
    embeddings: List[List[float]] = []
    for text in texts:
        result = genai.embed_content(
            model=settings.GEMINI_EMBEDDING_MODEL,
            content=text,
            task_type=task_type,
        )
        embeddings.append(result["embedding"])
    return embeddings


def embed_query(query: str) -> List[float]:
    """Generate a single query embedding."""
    return embed_texts([query], task_type="retrieval_query")[0]

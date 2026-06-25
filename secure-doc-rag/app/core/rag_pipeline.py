from typing import List, Tuple

import google.generativeai as genai

from app.config import settings
from app.core.embeddings import embed_query
from app.db.chroma_client import chroma_manager

genai.configure(api_key=settings.GEMINI_API_KEY)
_llm = genai.GenerativeModel(settings.GEMINI_LLM_MODEL)

_SYSTEM_PROMPT = """You are a helpful assistant that answers questions strictly based on the
provided document context. Follow these rules:
1. Answer ONLY from the context below. Do not use outside knowledge.
2. If the context does not contain enough information, say "I could not find relevant information
   in your documents."
3. Be concise and factual.
4. Never reveal or guess masked PII placeholders (e.g. [EMAIL], [SSN]).

Context:
{context}

Question: {question}

Answer:"""


def query_documents(
    customer_id: str,
    query: str,
    top_k: int = None,
) -> Tuple[str, List[str], int]:
    """
    Retrieve relevant chunks for *customer_id* and generate an answer.

    Returns:
        answer: generated text
        sources: list of source filenames
        chunks_used: number of context chunks fed to the LLM
    """
    if top_k is None:
        top_k = settings.TOP_K_RESULTS

    query_embedding = embed_query(query)
    results = chroma_manager.query(
        customer_id=customer_id,
        query_embedding=query_embedding,
        n_results=top_k,
    )

    docs: List[str] = results["documents"][0] if results["documents"] else []
    metas: List[dict] = results["metadatas"][0] if results["metadatas"] else []

    if not docs:
        return (
            "I could not find any documents for your account. Please upload documents first.",
            [],
            0,
        )

    context = "\n\n---\n\n".join(docs)
    sources = sorted({m.get("filename", "unknown") for m in metas})

    prompt = _SYSTEM_PROMPT.format(context=context, question=query)
    response = _llm.generate_content(prompt)
    answer = response.text.strip()

    return answer, sources, len(docs)

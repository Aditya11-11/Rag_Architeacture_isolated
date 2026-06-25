from typing import List, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import settings


class ChromaManager:
    """Manages a persistent ChromaDB client with per-customer collection isolation."""

    def __init__(self) -> None:
        self._client = chromadb.PersistentClient(
            path=settings.CHROMA_PERSIST_DIR,
            settings=ChromaSettings(anonymized_telemetry=False),
        )

    def _collection_name(self, customer_id: str) -> str:
        # Sanitise customer_id so it is a valid ChromaDB collection name
        safe = "".join(c if c.isalnum() else "_" for c in customer_id)
        return f"customer_{safe}"

    def get_or_create_collection(self, customer_id: str):
        return self._client.get_or_create_collection(
            name=self._collection_name(customer_id),
            metadata={"hnsw:space": "cosine"},
        )

    def add_documents(
        self,
        customer_id: str,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: List[dict],
    ) -> None:
        collection = self.get_or_create_collection(customer_id)
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    def query(
        self,
        customer_id: str,
        query_embedding: List[float],
        n_results: int,
        where: Optional[dict] = None,
    ) -> dict:
        collection = self.get_or_create_collection(customer_id)
        count = collection.count()
        if count == 0:
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

        effective_n = min(n_results, count)
        kwargs = dict(
            query_embeddings=[query_embedding],
            n_results=effective_n,
            include=["documents", "metadatas", "distances"],
        )
        if where:
            kwargs["where"] = where
        return collection.query(**kwargs)

    def list_documents(self, customer_id: str) -> dict:
        """Return all unique filenames and total chunk count for a customer."""
        collection = self.get_or_create_collection(customer_id)
        result = collection.get(include=["metadatas"])
        filenames = sorted({m.get("filename", "") for m in result["metadatas"]})
        return {"filenames": filenames, "total_chunks": len(result["ids"])}

    def delete_by_filename(self, customer_id: str, filename: str) -> int:
        collection = self.get_or_create_collection(customer_id)
        result = collection.get(where={"filename": filename}, include=["metadatas"])
        ids = result["ids"]
        if ids:
            collection.delete(ids=ids)
        return len(ids)

    def delete_all(self, customer_id: str) -> int:
        collection = self.get_or_create_collection(customer_id)
        result = collection.get(include=[])
        total = len(result["ids"])
        if total:
            collection.delete(ids=result["ids"])
        return total

    def close(self) -> None:
        pass  # PersistentClient flushes automatically


chroma_manager = ChromaManager()

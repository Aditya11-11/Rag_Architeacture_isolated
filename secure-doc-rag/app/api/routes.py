import os
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.config import settings
from app.core.document_processor import process_document
from app.core.embeddings import embed_texts
from app.core.rag_pipeline import query_documents
from app.db.chroma_client import chroma_manager
from app.models.schemas import (
    DeleteRequest,
    DeleteResponse,
    DocumentListResponse,
    QueryRequest,
    QueryResponse,
    UploadResponse,
)

router = APIRouter()

_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


@router.post("/documents/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    customer_id: str = Form(..., description="Unique customer identifier"),
    file: UploadFile = File(...),
) -> UploadResponse:
    ext = Path(file.filename).suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type '{ext}' is not supported. Allowed: {_ALLOWED_EXTENSIONS}",
        )

    content = await file.read()
    if len(content) > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {settings.MAX_FILE_SIZE_MB} MB limit.",
        )

    customer_dir = Path(settings.UPLOAD_DIR) / customer_id
    customer_dir.mkdir(parents=True, exist_ok=True)
    save_path = customer_dir / file.filename

    with open(save_path, "wb") as f:
        f.write(content)

    try:
        chunks = process_document(
            str(save_path),
            chunk_size=settings.CHUNK_SIZE,
            overlap=settings.CHUNK_OVERLAP,
        )
    except Exception as exc:
        save_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    if not chunks:
        save_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not extract any text from the document.",
        )

    texts = [c["text"] for c in chunks]
    embeddings = embed_texts(texts, task_type="retrieval_document")

    ids = [f"{customer_id}::{file.filename}::{c['chunk_index']}::{uuid.uuid4().hex[:8]}" for c in chunks]
    metadatas = [
        {
            "filename": file.filename,
            "chunk_index": c["chunk_index"],
            "customer_id": customer_id,
        }
        for c in chunks
    ]

    chroma_manager.add_documents(
        customer_id=customer_id,
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas,
    )

    return UploadResponse(
        customer_id=customer_id,
        filename=file.filename,
        chunks_stored=len(chunks),
        message=f"Successfully indexed {len(chunks)} chunks from '{file.filename}'.",
    )


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


@router.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest) -> QueryResponse:
    try:
        answer, sources, chunks_used = query_documents(
            customer_id=request.customer_id,
            query=request.query,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    return QueryResponse(
        customer_id=request.customer_id,
        query=request.query,
        answer=answer,
        sources=sources,
        context_chunks_used=chunks_used,
    )


# ---------------------------------------------------------------------------
# List documents
# ---------------------------------------------------------------------------


@router.get("/documents/{customer_id}", response_model=DocumentListResponse)
async def list_documents(customer_id: str) -> DocumentListResponse:
    info = chroma_manager.list_documents(customer_id)
    return DocumentListResponse(
        customer_id=customer_id,
        documents=info["filenames"],
        total_chunks=info["total_chunks"],
    )


# ---------------------------------------------------------------------------
# Delete documents
# ---------------------------------------------------------------------------


@router.delete("/documents", response_model=DeleteResponse)
async def delete_documents(request: DeleteRequest) -> DeleteResponse:
    if request.filename:
        deleted = chroma_manager.delete_by_filename(request.customer_id, request.filename)
        # Also remove the file from disk if present
        disk_path = Path(settings.UPLOAD_DIR) / request.customer_id / request.filename
        disk_path.unlink(missing_ok=True)
        msg = f"Deleted {deleted} chunks for file '{request.filename}'."
    else:
        deleted = chroma_manager.delete_all(request.customer_id)
        customer_dir = Path(settings.UPLOAD_DIR) / request.customer_id
        if customer_dir.exists():
            for f in customer_dir.iterdir():
                f.unlink(missing_ok=True)
        msg = f"Deleted all {deleted} chunks for customer '{request.customer_id}'."

    return DeleteResponse(
        customer_id=request.customer_id,
        message=msg,
        deleted_chunks=deleted,
    )

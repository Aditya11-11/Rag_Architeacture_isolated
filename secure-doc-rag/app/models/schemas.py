from pydantic import BaseModel, Field
from typing import Optional, List


class QueryRequest(BaseModel):
    customer_id: str = Field(..., description="Unique customer identifier")
    query: str = Field(..., min_length=1, description="Question to ask about the documents")


class QueryResponse(BaseModel):
    customer_id: str
    query: str
    answer: str
    sources: List[str]
    context_chunks_used: int


class UploadResponse(BaseModel):
    customer_id: str
    filename: str
    chunks_stored: int
    message: str


class DocumentListResponse(BaseModel):
    customer_id: str
    documents: List[str]
    total_chunks: int


class DeleteRequest(BaseModel):
    customer_id: str
    filename: Optional[str] = Field(
        None,
        description="Specific filename to delete. Omit to delete all documents for the customer.",
    )


class DeleteResponse(BaseModel):
    customer_id: str
    message: str
    deleted_chunks: int

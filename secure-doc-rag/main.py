import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.routes import router
from app.db.chroma_client import chroma_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)
    yield
    chroma_manager.close()


app = FastAPI(
    title="Secure Document Query System",
    description=(
        "RAG-based document query system with strict per-customer data isolation "
        "and automatic PII masking."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


@app.get("/", tags=["Health"])
async def root():
    return {"message": "Secure Document Query System", "status": "running"}


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy"}

import os
from pathlib import Path
from typing import List

import PyPDF2
from docx import Document

from app.core.pii_masker import mask_pii


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


def extract_text(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type '{ext}'. Supported: {SUPPORTED_EXTENSIONS}")

    if ext == ".pdf":
        return _extract_pdf(file_path)
    elif ext == ".docx":
        return _extract_docx(file_path)
    else:
        return _extract_txt(file_path)


def _extract_pdf(path: str) -> str:
    pages: List[str] = []
    with open(path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n".join(pages)


def _extract_docx(path: str) -> str:
    doc = Document(path)
    return "\n".join(para.text for para in doc.paragraphs if para.text.strip())


def _extract_txt(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def chunk_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    """Split *text* into overlapping chunks of at most *chunk_size* characters."""
    if not text.strip():
        return []

    chunks: List[str] = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == text_len:
            break
        start += chunk_size - overlap

    return chunks


def process_document(file_path: str, chunk_size: int, overlap: int) -> List[dict]:
    """
    Extract, mask PII, and chunk a document.

    Returns a list of dicts with keys: text, chunk_index, pii_types_masked.
    """
    raw_text = extract_text(file_path)
    masked_text, findings = mask_pii(raw_text)
    chunks = chunk_text(masked_text, chunk_size, overlap)

    filename = os.path.basename(file_path)
    return [
        {
            "text": chunk,
            "chunk_index": idx,
            "filename": filename,
            "pii_types_masked": findings,
        }
        for idx, chunk in enumerate(chunks)
    ]

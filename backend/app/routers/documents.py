"""Document ingestion. For now: PDF → extracted text (extraction only).

The text is returned to the client, not yet stored or embedded — that wiring
(RAG / graph memory) comes in a later slice. This router is the seam where that
lands.
"""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from app import pdf_extract

router = APIRouter()

# Generous cap so a stray huge upload can't exhaust memory. Tune as needed.
MAX_PDF_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    """Accept a text-based PDF and return its extracted text + basic metadata.

    Rejects non-PDFs, oversized files, and scanned/image-only PDFs (no OCR).
    """
    name = file.filename or "document.pdf"
    is_pdf = name.lower().endswith(".pdf") or file.content_type == "application/pdf"
    if not is_pdf:
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")

    data = await file.read()
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF is too large (max 10 MB).")

    try:
        doc = pdf_extract.extract_pdf(data, name)
    except pdf_extract.PdfError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "filename": doc.filename,
        "pages": doc.pages,
        "chars": doc.chars,
        "text": doc.text,
    }

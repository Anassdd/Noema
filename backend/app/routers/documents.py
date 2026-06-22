"""Document ingestion. PDF -> Docling structured parse (parse step only).

Docling replaces the old pypdf text dump (it keeps tables/structure/math and page
provenance, and runs locally). The parsed Markdown is returned to the client;
chunking + embedding into the retrieval store land in later slices. This router
is that seam.
"""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from app import docling_parse

router = APIRouter()

# Generous cap so a stray huge upload can't exhaust memory. Research PDFs run big.
MAX_PDF_BYTES = 25 * 1024 * 1024  # 25 MB


@router.post("/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    """Accept a PDF and return its Docling-parsed Markdown + basic metadata.

    Rejects non-PDFs and oversized files. Parsing failures (empty / scanned with
    OCR off) come back as a 400 with a clear message.
    """
    name = file.filename or "document.pdf"
    is_pdf = name.lower().endswith(".pdf") or file.content_type == "application/pdf"
    if not is_pdf:
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")

    data = await file.read()
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF is too large (max 25 MB).")

    try:
        doc = docling_parse.parse_pdf(data, name)
    except docling_parse.ParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "filename": doc.filename,
        "pages": doc.pages,
        "chars": doc.chars,
        "engine": doc.engine,
        "text": doc.markdown,
    }

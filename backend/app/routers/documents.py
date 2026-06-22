"""Document ingestion. PDF -> vision-LLM transcription (Markdown + LaTeX).

Pages are rendered locally (light) and transcribed by a vision model through the
provider abstraction — OpenAI on dev, the Azure-hosted OpenAI-compatible endpoint
in prod, swapped by `.env`. No heavy local models run here. This is the seam the
retrieval/graph slices build on.
"""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from app import parsing

router = APIRouter()

# Generous cap so a stray huge upload can't exhaust memory. Research PDFs run big.
MAX_PDF_BYTES = 25 * 1024 * 1024  # 25 MB


@router.post("/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    """Accept a PDF and return its vision-parsed Markdown + basic metadata.

    Rejects non-PDFs and oversized files. Parsing failures (unreadable / provider
    error) come back as a 400 with a clear message.
    """
    name = file.filename or "document.pdf"
    is_pdf = name.lower().endswith(".pdf") or file.content_type == "application/pdf"
    if not is_pdf:
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")

    data = await file.read()
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF is too large (max 25 MB).")

    try:
        doc = parsing.parse_document(data, name)  # vision or DI, per PARSER in .env
    except parsing.ParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "filename": doc.filename,
        "pages": doc.pages,
        "chars": doc.chars,
        "text": doc.markdown,
    }

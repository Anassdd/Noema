"""The co-occurrence graph memory surface.

Ingest text or a PDF, get back the salient word-network for the browser to render
(Sigma.js + graphology do the clustering/layout). The graph persists on disk, so
it's there again next time the page opens.
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app import parsing
from app.textgraph import TextGraphMemory

router = APIRouter(prefix="/textgraph")

# One shared memory for the single-domain phase; multi-domain is a keyed lookup later.
_memory = TextGraphMemory()

MAX_PDF_BYTES = 25 * 1024 * 1024


class IngestText(BaseModel):
    text: str
    source: str | None = None


@router.get("")
def get_graph(limit: int = 160) -> dict:
    return _memory.snapshot(limit=limit)


@router.post("/ingest")
def ingest_text(body: IngestText, limit: int = 160) -> dict:
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Nothing to add — the text is empty.")
    _memory.ingest(body.text, source=body.source or "pasted text")
    return _memory.snapshot(limit=limit)


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    model: str | None = Form(None),
    limit: int = 160,
) -> dict:
    name = file.filename or "document.pdf"
    is_pdf = name.lower().endswith(".pdf") or file.content_type == "application/pdf"
    if not is_pdf:
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")

    data = await file.read()
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF is too large (max 25 MB).")

    try:
        doc = parsing.parse_document(data, name, model=model or None)
    except parsing.ParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _memory.ingest(doc.markdown, source=doc.filename)
    return _memory.snapshot(limit=limit)


@router.post("/reset")
def reset() -> dict:
    _memory.reset()
    return _memory.snapshot()

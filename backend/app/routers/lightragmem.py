"""The LightRAG memory surface — same UX contract as /graphmem, second engine.

The 3D graph page talks to either engine through the same payload shape
({nodes, links, stats}) and the same NDJSON upload stream, so choosing an engine
in the UI swaps the URL prefix, nothing else. LightRAG is self-contained (its own
graph + vectors over its own chunks) — uploads here do NOT feed the shared RAG
vector base or the Graphiti graph.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app import parsing
from app.lightrag.manager import lightrag_manager
from app.routers.admin import block_bench_writes
from app.routers.auth import require_user

router = APIRouter(prefix="/lightragmem")

DOMAIN_DEFAULT = "default"
MAX_PDF_BYTES = 25 * 1024 * 1024
# Pages folded in per LightRAG pass — it extracts them concurrently inside one
# call, so batching beats page-by-page while still streaming regular snapshots.
PAGES_PER_BATCH = 4

_mgr = lightrag_manager


class IngestText(BaseModel):
    text: str
    source: str | None = None
    model: str | None = None
    domain: str | None = None


def _line(obj: dict) -> bytes:
    return (json.dumps(obj) + "\n").encode("utf-8")


@router.get("")
async def get_graph(domain: str = DOMAIN_DEFAULT) -> dict:
    mem = await _mgr.get(domain)
    return await mem.snapshot()


@router.post("/ingest")
async def ingest(body: IngestText, user: dict = Depends(require_user)) -> dict:
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Nothing to add — the text is empty.")
    domain = body.domain or DOMAIN_DEFAULT
    block_bench_writes(user, domain)
    mem = await _mgr.get(domain, body.model or "")
    async with _mgr.lock(domain):
        await mem.add_texts([body.text], [body.source or "pasted text"])
    return await mem.snapshot()


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    model: str | None = Form(None),
    domain: str = Form(DOMAIN_DEFAULT),
    user: dict = Depends(require_user),
) -> StreamingResponse:
    block_bench_writes(user, domain)
    name = file.filename or "document.pdf"
    is_pdf = name.lower().endswith(".pdf") or file.content_type == "application/pdf"
    if not is_pdf:
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")
    data = await file.read()
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF is too large (max 25 MB).")

    mem = await _mgr.get(domain, model or "")

    async def stream():
        yield _line({"phase": "parsing", "filename": name})
        try:
            doc = await asyncio.to_thread(parsing.parse_document, data, name)
        except parsing.ParseError as exc:
            yield _line({"phase": "error", "detail": str(exc)})
            return
        pages = [(i, p) for i, p in enumerate(doc.page_markdown) if p and p.strip()]
        yield _line({"phase": "parsed", "filename": doc.filename, "pages": len(pages)})

        async with _mgr.lock(domain):
            for start in range(0, len(pages), PAGES_PER_BATCH):
                batch = pages[start: start + PAGES_PER_BATCH]
                try:
                    await mem.add_texts(
                        [p for _, p in batch],
                        [f"{doc.filename} · p{i + 1}" for i, _ in batch],
                    )
                except Exception as exc:  # noqa: BLE001 — surface, keep going
                    yield _line({"phase": "error", "page": batch[0][0] + 1, "detail": str(exc)})
                    continue
                snap = await mem.snapshot()
                yield _line({"phase": "page", "page": start + len(batch),
                             "total": len(pages), **snap})
        yield _line({"phase": "done"})

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.post("/reset")
async def reset(domain: str = DOMAIN_DEFAULT, user: dict = Depends(require_user)) -> dict:
    block_bench_writes(user, domain)
    mem = await _mgr.get(domain)
    async with _mgr.lock(domain):
        await mem.wipe()
        await _mgr.drop(domain)
    mem = await _mgr.get(domain)
    return await mem.snapshot()

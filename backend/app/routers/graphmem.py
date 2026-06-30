"""The real graph memory surface — Graphiti (entities + relationships + temporal facts).

Unlike the co-occurrence `textgraph`, this is LLM-extracted, so it's the *real* memory:
nodes are entities, edges are facts with validity. Extraction is slow (one LLM pass per
episode), so PDF upload **streams** NDJSON — a fresh snapshot after each page — and the
3D page draws the graph as it grows. The graph persists in FalkorDB, so it's there next
time. The picked model is the **extraction** model (the one that builds the graph).
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app import parsing
from app.graph import GraphMemory, GraphSnapshot

router = APIRouter(prefix="/graphmem")

DOMAIN_DEFAULT = "default"
MAX_PDF_BYTES = 25 * 1024 * 1024


class _Manager:
    """Holds one GraphMemory per (domain, extraction-model); builds lazily, and
    serializes writes per domain so concurrent ingests don't race the graph."""

    def __init__(self) -> None:
        self._mems: dict[tuple[str, str], GraphMemory] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._build_lock = asyncio.Lock()

    async def get(self, domain: str, model: str = "") -> GraphMemory:
        key = (domain, model)
        mem = self._mems.get(key)
        if mem is None:
            async with self._build_lock:
                mem = self._mems.get(key)
                if mem is None:
                    mem = GraphMemory(domain, extract_model=model or None)
                    await mem.build()
                    self._mems[key] = mem
        return mem

    def lock(self, domain: str) -> asyncio.Lock:
        return self._locks.setdefault(domain, asyncio.Lock())


_mgr = _Manager()


class IngestText(BaseModel):
    text: str
    source: str | None = None
    model: str | None = None
    domain: str | None = None


def _payload(snap: GraphSnapshot) -> dict:
    ids = {n.uuid for n in snap.nodes}
    nodes = [
        {"id": n.uuid, "name": n.name, "labels": n.labels, "summary": n.summary}
        for n in snap.nodes
    ]
    links = [
        {
            "source": e.source_uuid,
            "target": e.target_uuid,
            "name": e.name,
            "fact": e.fact,
            "is_current": e.is_current,
            "valid_at": e.valid_at,
            "invalid_at": e.invalid_at,
        }
        for e in snap.edges
        if e.source_uuid in ids and e.target_uuid in ids
    ]
    current = sum(1 for l in links if l["is_current"])
    return {
        "nodes": nodes,
        "links": links,
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(links),
            "current_edges": current,
            "invalidated_edges": len(links) - current,
        },
    }


def _line(obj: dict) -> bytes:
    return (json.dumps(obj) + "\n").encode("utf-8")


@router.get("")
async def get_graph(domain: str = DOMAIN_DEFAULT) -> dict:
    mem = await _mgr.get(domain)
    return _payload(await mem.snapshot())


@router.post("/ingest")
async def ingest(body: IngestText) -> dict:
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Nothing to add — the text is empty.")
    domain = body.domain or DOMAIN_DEFAULT
    mem = await _mgr.get(domain, body.model or "")
    async with _mgr.lock(domain):
        await mem.add_episode(body.text, name=body.source or "pasted text")
    return _payload(await (await _mgr.get(domain)).snapshot())


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    model: str | None = Form(None),
    domain: str = Form(DOMAIN_DEFAULT),
) -> StreamingResponse:
    name = file.filename or "document.pdf"
    is_pdf = name.lower().endswith(".pdf") or file.content_type == "application/pdf"
    if not is_pdf:
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")
    data = await file.read()
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF is too large (max 25 MB).")

    mem = await _mgr.get(domain, model or "")
    reader = await _mgr.get(domain)

    async def stream():
        # Parse first (vision LLM, blocking → thread), then extract page by page.
        yield _line({"phase": "parsing", "filename": name})
        try:
            doc = await asyncio.to_thread(parsing.parse_document, data, name)
        except parsing.ParseError as exc:
            yield _line({"phase": "error", "detail": str(exc)})
            return
        pages = [p for p in doc.page_markdown if p and p.strip()]
        yield _line({"phase": "parsed", "filename": doc.filename, "pages": len(pages)})

        async with _mgr.lock(domain):
            for i, page in enumerate(pages):
                try:
                    await mem.add_episode(page, name=f"{doc.filename} · p{i + 1}")
                except Exception as exc:  # noqa: BLE001 — surface, keep going
                    yield _line({"phase": "error", "page": i + 1, "detail": str(exc)})
                    continue
                snap = await reader.snapshot()
                yield _line({"phase": "page", "page": i + 1, "total": len(pages), **_payload(snap)})
        yield _line({"phase": "done"})

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.post("/reset")
async def reset(domain: str = DOMAIN_DEFAULT) -> dict:
    mem = await _mgr.get(domain)
    await mem.reset()
    return _payload(await mem.snapshot())

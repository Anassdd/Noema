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
from app.graph.config import graph_config
from app.graph.manager import graph_manager
from app.retrieval import VectorStore, ingest_markdown, ingest_parsed_doc
from app.saves import save_key, save_prefix

router = APIRouter(prefix="/graphmem")

DOMAIN_DEFAULT = "default"
MAX_PDF_BYTES = 25 * 1024 * 1024


def _falkor_ops(fn):
    """Run a FalkorDB graph operation on the local server (a sync client in a thread).
    Used for full-graph save/restore via GRAPH.COPY — preserves everything."""
    from falkordb import FalkorDB

    db = FalkorDB(host=graph_config.host, port=graph_config.port)
    try:
        return fn(db)
    finally:
        try:
            db.close()
        except Exception:
            pass


# One shared cache of GraphMemory instances (also used by the retrieval pipeline).
_mgr = graph_manager


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
            "created_at": e.created_at,
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
    source = body.source or "pasted text"
    mem = await _mgr.get(domain, body.model or "")
    async with _mgr.lock(domain):
        await mem.add_episode(body.text, name=source)
    # Same text → also into the RAG vector base, so pasted text is queryable both ways
    # (chunk → contextualize → embed → store). Best-effort: never lose the graph write.
    try:
        await asyncio.to_thread(ingest_markdown, body.text, source, domain_id=domain)
    except Exception:
        pass
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

        # Same doc → also fold into the RAG vector base (chunk → contextualize → embed →
        # store), so the one corpus is queryable both ways. Reuses the already-parsed doc
        # (no second vision pass). Independent of the graph: a failure here must not lose
        # the graph work, so it's isolated and reported, not raised.
        yield _line({"phase": "rag_indexing", "filename": doc.filename})
        try:
            info = await asyncio.to_thread(
                ingest_parsed_doc, doc, domain_id=domain, context_model=model or None
            )
            yield _line({"phase": "rag_done", "filename": doc.filename, "chunks": info.get("chunks", 0)})
        except Exception as exc:  # noqa: BLE001 — surface, keep the stream alive
            yield _line({"phase": "rag_error", "filename": doc.filename, "detail": str(exc)})
        yield _line({"phase": "done"})

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.post("/reset")
async def reset(domain: str = DOMAIN_DEFAULT) -> dict:
    mem = await _mgr.get(domain)
    await mem.reset()
    return _payload(await mem.snapshot())


# ---- save / restore checkpoints (full-graph copies) -------------------------
class SaveBody(BaseModel):
    name: str
    domain: str | None = None


@router.get("/saves")
async def list_saves(domain: str = DOMAIN_DEFAULT) -> dict:
    prefix = save_prefix(domain)
    graphs = await asyncio.to_thread(_falkor_ops, lambda db: db.list_graphs())
    return {"saves": sorted(g[len(prefix):] for g in graphs if g.startswith(prefix))}


@router.post("/save")
async def save_graph(body: SaveBody) -> dict:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Give the save a name.")
    domain = body.domain or DOMAIN_DEFAULT
    await _mgr.get(domain)  # ensure the server is up and the graph exists
    dest = save_key(domain, name)

    def _do(db):
        if domain not in db.list_graphs():
            raise ValueError("empty")
        if dest in db.list_graphs():
            db.select_graph(dest).delete()  # overwrite an existing save of the same name
        db.select_graph(domain).copy(dest)

    async with _mgr.lock(domain):
        try:
            await asyncio.to_thread(_falkor_ops, _do)
        except ValueError:
            raise HTTPException(status_code=400, detail="Nothing to save — the graph is empty.")
        # Snapshot the RAG vector base under the same key, so the save captures BOTH stores.
        chunks = await asyncio.to_thread(lambda: VectorStore(domain).copy_into(dest))
    return {"saved": name, "chunks": chunks}


@router.post("/restore")
async def restore_graph(body: SaveBody) -> dict:
    name = body.name.strip()
    domain = body.domain or DOMAIN_DEFAULT
    src = save_key(domain, name)
    await _mgr.get(domain)

    def _do(db):
        if src not in db.list_graphs():
            raise ValueError("missing")
        if domain in db.list_graphs():
            db.select_graph(domain).delete()
        db.select_graph(src).copy(domain)

    async with _mgr.lock(domain):
        try:
            await asyncio.to_thread(_falkor_ops, _do)
        except ValueError:
            raise HTTPException(status_code=404, detail="That save doesn't exist.")
        # Restore the RAG store too (an old graph-only save has none → clears to empty).
        await asyncio.to_thread(lambda: VectorStore(src).copy_into(domain))
    mem = await _mgr.get(domain)
    return _payload(await mem.snapshot())


@router.post("/delete-save")
async def delete_save(body: SaveBody) -> dict:
    domain = body.domain or DOMAIN_DEFAULT
    name = body.name.strip()
    src = save_key(domain, name)

    def _do(db):
        if src in db.list_graphs():
            db.select_graph(src).delete()

    await asyncio.to_thread(_falkor_ops, _do)
    await asyncio.to_thread(lambda: VectorStore(src).drop())  # drop the RAG snapshot too
    return {"deleted": name}

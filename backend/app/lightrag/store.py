"""LightRAGMemory — the LightRAG strategy, one store per domain, behind the same
small surface as GraphMemory: build, add_texts, search, snapshot, reset.

LightRAG keeps a dual-level keyword graph AND its own vector base over the same
chunks, so it is self-contained — nothing here touches the Graphiti graph or the
contextual RAG store. Everything persists as files under one workspace directory
(<root>/<domain>), which is what saves copy and restore.
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from lightrag import LightRAG, QueryParam
from lightrag.kg.shared_storage import initialize_pipeline_status

from app.config import settings
from app.lightrag.providers import build_embedding_func, build_llm_func, extraction_model_name


def lightrag_root() -> Path:
    if settings.lightrag_dir:
        return Path(settings.lightrag_dir)
    return Path(__file__).resolve().parents[2] / "data" / "lightrag"


def workspace_dir(domain_id: str) -> Path:
    """Where one domain's whole LightRAG store lives — the unit saves copy."""
    return lightrag_root() / domain_id


def _iso(ts) -> str | None:
    """LightRAG stamps nodes/edges with unix seconds; the frontend timeline wants ISO."""
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


class LightRAGMemory:
    """One LightRAG store for one domain. Construct, then `await build()` once."""

    def __init__(self, domain_id: str = "default", *, extract_model: str | None = None):
        self.domain_id = domain_id
        self.extract_model = extract_model or ""
        extract = extraction_model_name(extract_model)
        cheap = build_llm_func(settings.chat_model)
        lightrag_root().mkdir(parents=True, exist_ok=True)
        self.rag = LightRAG(
            working_dir=str(lightrag_root()),
            workspace=domain_id,
            llm_model_func=build_llm_func(extract),
            llm_model_name=extract,
            # Query-time keyword extraction is a cheap routing task — no need to
            # burn the strong extraction model on it.
            role_llm_configs={"keyword": {"func": cheap}, "query": {"func": cheap}},
            embedding_func=build_embedding_func(),
        )

    async def build(self) -> "LightRAGMemory":
        await self.rag.initialize_storages()
        await initialize_pipeline_status(self.domain_id)
        return self

    # ---- ingestion --------------------------------------------------------
    async def add_texts(self, texts: list[str], sources: list[str]) -> None:
        """Fold texts in (chunk → extract → merge into the keyword graph + vectors).
        `sources` become each piece's provenance (file_path) — we pass
        '<file> · p<N>' so retrieved facts can cite document + page."""
        await self.rag.ainsert(list(texts), file_paths=list(sources))

    # ---- retrieval --------------------------------------------------------
    async def search(self, query: str, *, limit: int = 10) -> dict:
        """LightRAG's own retrieval (mix mode: dual-level keywords over graph +
        vectors), WITHOUT its generation step — the pipeline keeps one shared
        grounded-answer path for every memory method. Returns {'relations': [...],
        'chunks': [...]} rows, each already relevance-ranked."""
        res = await self.rag.aquery_data(
            query,
            QueryParam(mode="mix", top_k=max(limit * 2, 20), chunk_top_k=limit,
                       enable_rerank=False),
        )
        data = res.get("data") or {}
        relations = [
            {
                "source": r.get("src_id", "?"),
                "target": r.get("tgt_id", "?"),
                "keywords": r.get("keywords", ""),
                "text": r.get("description", ""),
                "file_path": r.get("file_path", ""),
            }
            for r in data.get("relationships", [])
        ]
        chunks = [
            {
                "id": c.get("chunk_id", ""),
                "text": c.get("content", ""),
                "file_path": c.get("file_path", ""),
            }
            for c in data.get("chunks", [])
        ]
        return {"relations": relations, "chunks": chunks}

    # ---- inspection -------------------------------------------------------
    async def snapshot(self, max_nodes: int = 1000) -> dict:
        """The graph as the 3D page draws it — same payload shape as /graphmem, so
        the frontend renders either engine unchanged. LightRAG has no temporal
        invalidation, so every edge is current."""
        kg = await self.rag.get_knowledge_graph("*", max_nodes=max_nodes)
        nodes = [
            {
                "id": n.id,
                "name": n.properties.get("entity_id", n.id),
                "labels": [n.properties.get("entity_type", "entity")],
                "summary": n.properties.get("description", ""),
            }
            for n in kg.nodes
        ]
        ids = {n["id"] for n in nodes}
        links = [
            {
                "source": e.source,
                "target": e.target,
                "name": e.properties.get("keywords", "") or (e.type or ""),
                "fact": e.properties.get("description", ""),
                "is_current": True,
                "valid_at": None,
                "invalid_at": None,
                "created_at": _iso(e.properties.get("created_at")),
            }
            for e in kg.edges
            if e.source in ids and e.target in ids
        ]
        return {
            "nodes": nodes,
            "links": links,
            "stats": {
                "node_count": len(nodes),
                "edge_count": len(links),
                "current_edges": len(links),
                "invalidated_edges": 0,
            },
        }

    # ---- maintenance ------------------------------------------------------
    async def close(self) -> None:
        try:
            await self.rag.finalize_storages()
        except Exception:
            pass

    async def wipe(self) -> None:
        """Delete this domain's whole store from disk. The manager drops the cached
        instance right after, so the next access rebuilds an empty one."""
        await self.close()
        shutil.rmtree(workspace_dir(self.domain_id), ignore_errors=True)

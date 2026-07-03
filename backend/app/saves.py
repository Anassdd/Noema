"""Saved memory snapshots ("saves") — named checkpoints of a domain's whole memory.

A save captures BOTH stores under one key so they stay in lockstep: the Graphiti graph
(a FalkorDB graph, copied via GRAPH.COPY) and the RAG vector base (a Chroma collection).
This module owns the naming scheme AND the operations; routers stay thin.

Imports of the graph/retrieval layers are lazy — app.graph.store imports base_group_id
from here at module load, so a top-level import back into app.graph would be circular.
"""

from __future__ import annotations

SAVE_PREFIX = "__save__"


def save_key(domain: str, name: str) -> str:
    return f"{SAVE_PREFIX}{domain}__{name}"


def save_prefix(domain: str) -> str:
    return f"{SAVE_PREFIX}{domain}__"


def base_group_id(domain_id: str) -> str:
    """The group_id the DATA carries. A save graph is a raw copy of its base domain, so its
    nodes keep the base domain's group_id (e.g. '__save__default__v1' → 'default'). The graph
    to CONNECT to is `domain_id`; the group_id to FILTER by is this. They differ only for saves."""
    if domain_id.startswith(SAVE_PREFIX):
        return domain_id[len(SAVE_PREFIX):].split("__", 1)[0]
    return domain_id


# ---- operations (sync — async callers wrap in asyncio.to_thread) -------------
def list_saves(domain: str) -> list[str]:
    from app.graph.server import list_graphs

    prefix = save_prefix(domain)
    return sorted(g[len(prefix):] for g in list_graphs() if g.startswith(prefix))


def create_save(domain: str, name: str) -> int:
    """Checkpoint both stores under the save key. Returns the chunk count captured
    from the vector base. Raises ValueError if the graph is empty."""
    from app.graph.server import falkor_ops
    from app.retrieval import VectorStore

    dest = save_key(domain, name)

    def _copy(db):
        if domain not in db.list_graphs():
            raise ValueError("empty")
        if dest in db.list_graphs():
            db.select_graph(dest).delete()
        db.select_graph(domain).copy(dest)

    falkor_ops(_copy)
    return VectorStore(domain).copy_into(dest)


def restore_save(domain: str, name: str) -> None:
    """Overwrite the live domain with the save — both stores. Raises ValueError if
    the save doesn't exist. An old graph-only save restores an empty vector base."""
    from app.graph.server import falkor_ops
    from app.retrieval import VectorStore

    src = save_key(domain, name)

    def _copy(db):
        if src not in db.list_graphs():
            raise ValueError("missing")
        if domain in db.list_graphs():
            db.select_graph(domain).delete()
        db.select_graph(src).copy(domain)

    falkor_ops(_copy)
    VectorStore(src).copy_into(domain)


def delete_save(domain: str, name: str) -> None:
    from app.graph.server import drop_graph
    from app.retrieval import VectorStore

    src = save_key(domain, name)
    drop_graph(src)
    VectorStore(src).drop()

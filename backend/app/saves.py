"""Saved memory snapshots ("saves") — named checkpoints, scoped per memory engine.

A save belongs to ONE engine. A Graphiti save captures the graph (a FalkorDB graph,
via GRAPH.COPY) together with its RAG vector base (a Chroma collection) — they answer
together in hybrid mode, so they checkpoint together. A LightRAG save captures that
engine's whole workspace directory (it is self-contained: own graph + own vectors).
Both engines share the one naming scheme, so the same name may exist in each engine —
they are separate checkpoints, and touching one never touches the other.

This module owns the naming scheme AND the operations; routers stay thin.

Imports of the graph/retrieval layers are lazy — app.graph.store imports base_group_id
from here at module load, so a top-level import back into app.graph would be circular.
"""

from __future__ import annotations

import re
import shutil

SAVE_PREFIX = "__save__"
# Bench builds land in saves named "bench-…" (bench/runner.py) — expensive frozen
# benchmark corpora, guarded against non-admin modification (routers/admin.py).
BENCH_SAVE_PREFIX = "bench-"


def save_key(domain: str, name: str) -> str:
    return f"{SAVE_PREFIX}{domain}__{name}"


def is_bench_artifact(domain_id: str = "", name: str = "") -> bool:
    """True when a save name or a full '__save__<domain>__<name>' domain id points
    at bench-built content."""
    if name.startswith(BENCH_SAVE_PREFIX):
        return True
    if not domain_id.startswith(SAVE_PREFIX):
        return False
    rest = domain_id[len(SAVE_PREFIX):]
    return "__" in rest and rest.split("__", 1)[1].startswith(BENCH_SAVE_PREFIX)


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
def _has_lightrag(domain: str) -> bool:
    from app.lightrag import workspace_dir

    d = workspace_dir(domain)
    return d.exists() and any(d.iterdir())


def _graphiti_names(domain: str) -> set[str]:
    from app.graph.server import list_graphs

    prefix = save_prefix(domain)
    return {g[len(prefix):] for g in list_graphs() if g.startswith(prefix)}


def _lightrag_names(domain: str) -> set[str]:
    from app.lightrag.store import lightrag_root

    prefix = save_prefix(domain)
    root = lightrag_root()
    if not root.exists():
        return set()
    return {d.name[len(prefix):] for d in root.iterdir()
            if d.is_dir() and d.name.startswith(prefix)}


def list_saves(domain: str, engine: str = "") -> list[str]:
    """RAW stored save names for one engine — "graphiti" (has a Falkor graph),
    "lightrag" (has a LightRAG workspace), or "" for the union. Internal view
    (bench, ops): user-facing surfaces go through `visible_saves` instead."""
    if engine == "graphiti":
        return sorted(_graphiti_names(domain))
    if engine == "lightrag":
        return sorted(_lightrag_names(domain))
    return sorted(_graphiti_names(domain) | _lightrag_names(domain))


# ---- per-user saves ----------------------------------------------------------
# A personal save is stored under "u<uid>__<name>" (uid = auth_store.user_uid, an
# 8-hex id that survives renames). Names without that prefix are SHARED — visible
# to everyone, created by admins (and by history: bench builds, pre-accounts saves).
_PERSONAL_RE = re.compile(r"^u([0-9a-f]{8})__(.+)$")


def personal_name(uid: str, name: str) -> str:
    return f"u{uid}__{name}"


def split_owner(stored: str) -> tuple[str | None, str]:
    """(owner uid, display name) for a stored save name; owner None = shared."""
    m = _PERSONAL_RE.match(stored)
    return (m.group(1), m.group(2)) if m else (None, stored)


def visible_saves(domain: str, uid: str) -> list[dict]:
    """What ONE user may see: every shared save plus their own personal ones —
    each as {name (display), mine, engines:[...]}. Other users' personal saves
    stay invisible. `engines` is what makes the UI existence-aware: a save that
    only exists for one engine must not be selectable with the other's retrieval."""
    entries: dict[tuple[str | None, str], dict] = {}
    for engine, names in (("graphiti", _graphiti_names(domain)),
                          ("lightrag", _lightrag_names(domain))):
        for stored in names:
            owner, display = split_owner(stored)
            if owner is not None and owner != uid:
                continue
            entry = entries.setdefault(
                (owner, display), {"name": display, "mine": owner is not None, "engines": []})
            entry["engines"].append(engine)
    return sorted(entries.values(), key=lambda e: (e["mine"], e["name"].lower()))


def resolve_stored(domain: str, name: str, uid: str) -> str:
    """The stored save name a user's display `name` points at: their own copy wins
    over a shared save of the same name. Falls through to the shared name (a
    missing save then fails downstream with the normal 'doesn't exist' error)."""
    personal = personal_name(uid, name)
    if personal in _graphiti_names(domain) | _lightrag_names(domain):
        return personal
    return name


def _copy_lightrag(src_domain: str, dest_domain: str) -> None:
    """Mirror the LightRAG workspace dir from one domain key to another. The dest
    is always cleared first, so a source without LightRAG data leaves the dest
    empty — the same lockstep rule as the vector base."""
    from app.lightrag import workspace_dir

    src, dest = workspace_dir(src_domain), workspace_dir(dest_domain)
    shutil.rmtree(dest, ignore_errors=True)
    if src.exists():
        shutil.copytree(src, dest)


def create_save(domain: str, name: str, engine: str = "graphiti") -> int:
    """Checkpoint ONE engine's memory under the save key. Graphiti = graph + vector
    base; LightRAG = its workspace dir. The other engine's save of the same name (if
    any) is left untouched. Returns the vector-chunk count captured (0 for LightRAG).
    Raises ValueError when the chosen engine's memory is empty."""
    dest = save_key(domain, name)

    if engine == "lightrag":
        if not _has_lightrag(domain):
            raise ValueError("empty")
        _copy_lightrag(domain, dest)
        return 0

    from app.graph.server import falkor_ops
    from app.retrieval import VectorStore

    def _copy(db):
        if domain not in db.list_graphs():
            raise ValueError("empty")
        if dest in db.list_graphs():
            db.select_graph(dest).delete()
        db.select_graph(domain).copy(dest)

    falkor_ops(_copy)
    return VectorStore(domain).copy_into(dest)


def restore_save(domain: str, name: str, engine: str = "graphiti") -> None:
    """Overwrite ONE engine's live memory with its save — the other engine's live
    memory is never touched. Raises ValueError if that engine has no save by this
    name. For LightRAG the caller must drop the cached live instance first (its
    state lives in memory) — see the graphmem restore route."""
    src = save_key(domain, name)

    if engine == "lightrag":
        if name not in _lightrag_names(domain):
            raise ValueError("missing")
        _copy_lightrag(src, domain)
        return

    from app.graph.server import falkor_ops
    from app.retrieval import VectorStore

    if name not in _graphiti_names(domain):
        raise ValueError("missing")

    def _copy(db):
        if domain in db.list_graphs():
            db.select_graph(domain).delete()
        db.select_graph(src).copy(domain)

    falkor_ops(_copy)
    VectorStore(src).copy_into(domain)


def delete_save(domain: str, name: str, engine: str = "graphiti") -> None:
    """Delete ONE engine's save; the same name in the other engine survives."""
    src = save_key(domain, name)

    if engine == "lightrag":
        from app.lightrag import workspace_dir

        shutil.rmtree(workspace_dir(src), ignore_errors=True)
        return

    from app.graph.server import drop_graph
    from app.retrieval import VectorStore

    drop_graph(src)
    VectorStore(src).drop()

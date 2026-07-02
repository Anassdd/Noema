"""Naming for saved memory snapshots.

A "save" is a named checkpoint of a domain's memory. It captures BOTH stores — the
Graphiti graph (a FalkorDB graph) and the RAG vector base (a Chroma collection) — under
one key, so the graph store, the vector store, and the retrieval pipeline all agree on it.
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

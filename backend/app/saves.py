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

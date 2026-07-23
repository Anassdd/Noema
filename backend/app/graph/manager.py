"""Shared cache of GraphMemory instances — one per (domain, extraction-model).

Both the graphmem router (which WRITES the graph) and the retrieval pipeline (which
READS it to answer) go through this single cache, so there is exactly one FalkorDriver
per domain, bound to the app's event loop. A second, independent instance would open a
second driver and risk the "event loop is closed" class of bugs.

Writes per domain are serialized with `lock(domain)`; reads (search/snapshot) don't take it.
"""

from __future__ import annotations

import asyncio

from app.graph.store import GraphMemory


class GraphManager:
    def __init__(self) -> None:
        self._mems: dict[tuple[str, str, str], GraphMemory] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._build_lock = asyncio.Lock()

    async def get(self, domain: str, model: str = "",
                  effort: str = "") -> GraphMemory:
        key = (domain, model, effort)
        mem = self._mems.get(key)
        if mem is None:
            async with self._build_lock:
                mem = self._mems.get(key)
                if mem is None:
                    mem = GraphMemory(domain, extract_model=model or None,
                                      extract_effort=effort or None)
                    await mem.build()
                    self._mems[key] = mem
        return mem

    def lock(self, domain: str) -> asyncio.Lock:
        return self._locks.setdefault(domain, asyncio.Lock())


graph_manager = GraphManager()

"""Shared cache of LightRAGMemory instances — exactly ONE per domain.

Unlike Graphiti (a server every instance reads live), LightRAG holds its graph and
vectors IN MEMORY and flushes to files — two instances over one workspace would go
stale against each other. So the cache is keyed by domain alone; asking for a
different extraction model replaces the instance instead of adding a second one,
and anything that rewrites the files on disk (restore, reset) must `drop()` the
cached instance so the next access reloads.

Writes per domain are serialized with `lock(domain)`; reads don't take it.
"""

from __future__ import annotations

import asyncio

from app.lightrag.store import LightRAGMemory


class LightRAGManager:
    def __init__(self) -> None:
        self._mems: dict[str, LightRAGMemory] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._build_lock = asyncio.Lock()

    async def get(self, domain: str, model: str = "") -> LightRAGMemory:
        async with self._build_lock:
            mem = self._mems.get(domain)
            if mem is None or (model and mem.extract_model != model):
                if mem is not None:
                    await mem.close()
                mem = await LightRAGMemory(domain, extract_model=model or None).build()
                self._mems[domain] = mem
        return mem

    def lock(self, domain: str) -> asyncio.Lock:
        return self._locks.setdefault(domain, asyncio.Lock())

    async def drop(self, domain: str) -> None:
        async with self._build_lock:
            mem = self._mems.pop(domain, None)
        if mem is not None:
            await mem.close()


lightrag_manager = LightRAGManager()

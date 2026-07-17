"""Persistent co-occurrence graph memory.

The graph *is* the memory, so it lives on disk (one JSON per domain) and grows
incrementally — every ingested document folds into the running counts, nothing is
rebuilt. `snapshot` returns the salient sub-network (top nodes by frequency) for
the UI to lay out; all the visual work (clustering, sizing, force layout) happens
in the browser, so the backend only keeps the raw weighted graph.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from .cooccurrence import accumulate, tokenize

from app.config import state_path

STORE_DIR = state_path("textgraph", Path(__file__).resolve().parent.parent / "textgraph_store")
DEFAULT_LIMIT = 160  # max nodes returned to the UI — keeps the network legible


class TextGraphMemory:
    def __init__(self, domain: str = "default") -> None:
        self.domain = domain
        self.path = STORE_DIR / f"{domain}.json"
        self._lock = threading.Lock()
        self._node_counts: dict[str, int] = {}
        self._edge_weights: dict[str, float] = {}
        self._sources: list[str] = []
        self._token_count = 0
        self._load()

    # ---- persistence ---------------------------------------------------------
    def _load(self) -> None:
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self._node_counts = data.get("nodes", {})
        self._edge_weights = data.get("edges", {})
        self._sources = data.get("sources", [])
        self._token_count = data.get("token_count", 0)

    def _save(self) -> None:
        STORE_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "domain": self.domain,
            "nodes": self._node_counts,
            "edges": self._edge_weights,
            "sources": self._sources,
            "token_count": self._token_count,
        }
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(self.path)

    # ---- mutation ------------------------------------------------------------
    def ingest(self, text: str, *, source: str | None = None) -> dict:
        with self._lock:
            tokens = tokenize(text)
            accumulate(tokens, self._node_counts, self._edge_weights)
            self._token_count += len(tokens)
            if source:
                self._sources.append(source)
            self._save()
            return {"tokens": len(tokens), "added_from": source}

    def reset(self) -> None:
        with self._lock:
            self._node_counts.clear()
            self._edge_weights.clear()
            self._sources.clear()
            self._token_count = 0
            if self.path.exists():
                self.path.unlink()

    # ---- read ----------------------------------------------------------------
    def snapshot(self, limit: int = DEFAULT_LIMIT) -> dict:
        with self._lock:
            kept = sorted(self._node_counts, key=self._node_counts.get, reverse=True)[:limit]
            keep = set(kept)
            nodes = [{"id": w, "label": w, "count": self._node_counts[w]} for w in kept]
            edges = []
            for key, weight in self._edge_weights.items():
                a, b = key.split("\t", 1)
                if a in keep and b in keep:
                    edges.append({"source": a, "target": b, "weight": round(weight, 3)})
            return {
                "nodes": nodes,
                "edges": edges,
                "stats": {
                    "node_count": len(self._node_counts),
                    "edge_count": len(self._edge_weights),
                    "shown_nodes": len(nodes),
                    "shown_edges": len(edges),
                    "doc_count": len(self._sources),
                    "token_count": self._token_count,
                    "sources": self._sources,
                },
            }

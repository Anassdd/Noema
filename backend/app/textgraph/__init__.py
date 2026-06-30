"""Co-occurrence text-network memory (the InfraNodus-style graph).

A second, instant memory built from word co-occurrence — no LLM, computed on
ingest, persisted per domain. Distinct from the Graphiti entity graph in
`app.graph`: same documents, a lighter lens that reacts the moment text arrives.

Public API:
    TextGraphMemory(domain) -> .ingest(text, source) / .snapshot(limit) / .reset()
"""

from app.textgraph.store import TextGraphMemory

__all__ = ["TextGraphMemory"]

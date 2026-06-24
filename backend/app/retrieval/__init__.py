"""Retrieval package — the contextual vector base (built incrementally).

So far: contextualization (Anthropic Contextual Retrieval). Next: embed -> store ->
hybrid search (dense + BM25) -> rerank. See CONTEXTUAL.md.

Public API:
    contextualize_chunks(document_markdown, chunks) -> list[ContextualChunk]
    contextualize_chunk(document_markdown, chunk)   -> ContextualChunk
    ContextualChunk
"""

from app.retrieval.contextual import (ContextualChunk, contextualize_chunk,
                                      contextualize_chunks)

__all__ = ["ContextualChunk", "contextualize_chunk", "contextualize_chunks"]

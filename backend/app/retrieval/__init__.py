"""Retrieval package — the contextual vector base (the queryable memory).

Pipeline: contextualize -> embed + store -> hybrid search (dense + BM25, fused) ->
optional rerank -> grounded, cited answer. See CONTEXTUAL.md and RETRIEVAL.md.

Public API:
    contextualize_chunks(document_markdown, chunks) -> list[ContextualChunk]
    ingest_pdf(data, filename) / ingest_markdown(markdown, doc_id)  -> store the doc
    search(query) -> list[ScoredChunk]      ·  search_trace(query) -> RetrievalTrace
    answer(query) -> Answer                  (grounded, cited)
    VectorStore, ScoredChunk, RetrievalTrace, Answer
"""

from app.retrieval.answer import answer, answer_from
from app.retrieval.base import Answer, RetrievalTrace, ScoredChunk
from app.retrieval.contextual import (ContextualChunk, contextualize_chunk,
                                      contextualize_chunks)
from app.retrieval.ingest import ingest_markdown, ingest_parsed_doc, ingest_pdf
from app.retrieval.search import rrf, search, search_trace
from app.retrieval.store import VectorStore

__all__ = [
    "ContextualChunk", "contextualize_chunk", "contextualize_chunks",
    "ingest_pdf", "ingest_parsed_doc", "ingest_markdown", "VectorStore",
    "rrf", "search", "search_trace", "answer", "answer_from",
    "ScoredChunk", "RetrievalTrace", "Answer",
]

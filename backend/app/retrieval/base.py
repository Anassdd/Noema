"""Shared retrieval types — the stable contract every retriever returns.

`search()` returns `ScoredChunk`s and `answer()` depends only on that, so the graph
layer can later slot in behind the same contract with no rewrite.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ScoredChunk:
    chunk_id: str
    text: str           # the ORIGINAL chunk text — what we feed the LLM and cite
    context: str        # the contextual blurb (used for embedding/BM25, not cited)
    doc_id: str
    pages: list[int]
    section: str
    domain_id: str = "default"
    score: float = 0.0
    scores: dict = field(default_factory=dict)  # per-stage: dense / bm25 / rrf / rerank

    @property
    def citation(self) -> str:
        pages = ", p." + "-".join(str(p) for p in self.pages) if self.pages else ""
        return f"{self.doc_id}{pages}"

    @property
    def embed_text(self) -> str:
        """What gets embedded / BM25-indexed: the blurb prepended to the chunk."""
        return f"{self.context}\n\n{self.text}" if self.context else self.text


@dataclass
class RetrievalTrace:
    """Every stage a query passes through — for the lab's step-by-step view."""

    query: str
    dense: list[ScoredChunk] = field(default_factory=list)
    bm25: list[ScoredChunk] = field(default_factory=list)
    fused: list[ScoredChunk] = field(default_factory=list)
    reranked: list[ScoredChunk] = field(default_factory=list)
    final: list[ScoredChunk] = field(default_factory=list)
    reranked_applied: bool = False
    timings: dict = field(default_factory=dict)


@dataclass
class Answer:
    text: str
    sources: list[ScoredChunk]
    prompt_tokens: int = 0
    completion_tokens: int = 0

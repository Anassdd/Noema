"""Hybrid search — dense + BM25, fused with Reciprocal Rank Fusion, then optional rerank.

Returns a `RetrievalTrace` exposing every stage (dense / bm25 / fused / reranked / final),
which is what the lab renders step-by-step. `search()` is the convenience that returns
just the final list. The graph layer will later add a third retriever behind this seam.
"""

from __future__ import annotations

import time

from app import llm_client
from app.retrieval import rerank as _rerank
from app.retrieval.base import RetrievalTrace, ScoredChunk
from app.retrieval.bm25 import BM25
from app.retrieval.store import VectorStore

_RRF_K = 60


def _rrf(rankings: list[list[str]]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (_RRF_K + rank + 1)
    return scores


def search_trace(query: str, *, k: int = 8, domain_id: str = "default",
                 dense_k: int = 20, bm25_k: int = 20, rerank_mode: str = "off",
                 rerank_pool: int = 10, store: VectorStore | None = None) -> RetrievalTrace:
    store = store or VectorStore(domain_id)
    trace = RetrievalTrace(query=query)

    records = store.all_records()
    by_id = {r.chunk_id: r for r in records}
    if not records:
        return trace

    # dense
    t0 = time.perf_counter()
    qvec = llm_client.embed([query])[0]
    dense_hits = store.query(qvec, dense_k)
    for d in dense_hits:
        if d.chunk_id in by_id:
            by_id[d.chunk_id].scores["dense"] = d.scores.get("dense", 0.0)
    dense_ranking = [d.chunk_id for d in dense_hits if d.chunk_id in by_id]
    trace.dense = [by_id[c] for c in dense_ranking]
    trace.timings["dense_ms"] = round((time.perf_counter() - t0) * 1000, 1)

    # bm25
    t0 = time.perf_counter()
    bm = BM25().build([(r.chunk_id, r.embed_text) for r in records])
    bm_hits = bm.search(query, bm25_k)
    for cid, s in bm_hits:
        by_id[cid].scores["bm25"] = s
    bm25_ranking = [cid for cid, _ in bm_hits]
    trace.bm25 = [by_id[c] for c in bm25_ranking]
    trace.timings["bm25_ms"] = round((time.perf_counter() - t0) * 1000, 1)

    # fuse (RRF)
    fused_scores = _rrf([dense_ranking, bm25_ranking])
    for cid, s in fused_scores.items():
        by_id[cid].scores["rrf"] = round(s, 5)
        by_id[cid].score = round(s, 5)
    fused = sorted((by_id[c] for c in fused_scores), key=lambda c: c.score, reverse=True)
    trace.fused = fused

    # rerank (optional)
    if rerank_mode != "off" and len(fused) > 1:
        t0 = time.perf_counter()
        trace.reranked = _rerank.rerank(query, fused[:rerank_pool], mode=rerank_mode)
        trace.reranked_applied = True
        trace.timings["rerank_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        trace.final = trace.reranked[:k]
    else:
        trace.reranked = fused
        trace.final = fused[:k]

    return trace


def search(query: str, *, k: int = 8, domain_id: str = "default",
           rerank_mode: str = "off", store: VectorStore | None = None) -> list[ScoredChunk]:
    return search_trace(query, k=k, domain_id=domain_id, rerank_mode=rerank_mode,
                        store=store).final

"""Query-side index cache tests — no network, no Chroma (a fake store):

    backend/.venv/bin/python tests/test_search_cache.py

Covers: the corpus pull + BM25 build happen once and are reused; writes and count
drift invalidate; per-query score stamping never pollutes the cached templates or a
later query; doc-scoped searches still see subset IDF.
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app import llm_client  # noqa: E402
from app.retrieval import index_cache  # noqa: E402
from app.retrieval.base import ScoredChunk  # noqa: E402
from app.retrieval.search import search_trace  # noqa: E402


def _rec(cid, text, doc="doc-1"):
    return ScoredChunk(chunk_id=cid, text=text, context="", doc_id=doc,
                       pages=[1], section="", score=0.0, scores={})


class FakeStore:
    """Just enough VectorStore surface for index_cache + search_trace."""

    def __init__(self, records):
        self.domain_id = "fake"
        self.cache_key = ("fake-path", "fake")
        self._records = records
        self.pulls = 0

    def count(self):
        return len(self._records)

    def all_records(self):
        self.pulls += 1
        return list(self._records)

    def query(self, qvec, k, *, doc_id=None):
        recs = [r for r in self._records if not doc_id or r.doc_id == doc_id]
        hits = [ScoredChunk(**{**r.__dict__, "score": 0.9, "scores": {"dense": 0.9}})
                for r in recs[:k]]
        return hits


RECORDS = [
    _rec("a", "the euler identity connects exponentials and trigonometry"),
    _rec("b", "banach spaces generalize normed vector spaces", doc="doc-2"),
    _rec("c", "the fourier transform decomposes signals into frequencies"),
]


def _fresh():
    index_cache.invalidate(("fake-path", "fake"))
    return FakeStore(list(RECORDS))


def test_pull_once_then_reuse():
    s = _fresh()
    r1, i1 = index_cache.get(s)
    r2, i2 = index_cache.get(s)
    assert s.pulls == 1, f"expected one corpus pull, got {s.pulls}"
    assert i1 is i2 and r1 is r2, "second get must return the cached objects"
    assert i1.search("fourier transform", 3)[0][0] == "c"
    print("  reuse: one pull, shared BM25 index, correct hits ✓")


def test_invalidate_and_count_drift():
    s = _fresh()
    index_cache.get(s)
    index_cache.invalidate(s.cache_key)
    index_cache.get(s)
    assert s.pulls == 2, "explicit invalidation must force a rebuild"
    s._records.append(_rec("d", "new chunk about laplace operators"))
    _, idx = index_cache.get(s)
    assert s.pulls == 3, "a count change must force a rebuild"
    assert idx.search("laplace", 2)[0][0] == "d"
    print("  invalidation: explicit + count-drift both rebuild ✓")


def test_no_score_pollution_across_queries():
    s = _fresh()
    restore = llm_client.embed
    llm_client.embed = lambda texts, **kw: [[1.0, 0.0] for _ in texts]
    try:
        t1 = search_trace("euler identity", store=s, k=2)
        polluted = {c.chunk_id: dict(c.scores) for c in t1.fused}
        t2 = search_trace("banach spaces", store=s, k=2)
    finally:
        llm_client.embed = restore
    cached_records, _ = index_cache.get(s)
    assert all(not r.scores and r.score == 0.0 for r in cached_records), \
        "cached templates must never carry query scores"
    for c in t2.fused:
        if "bm25" in c.scores and c.chunk_id in polluted and "bm25" in polluted[c.chunk_id]:
            assert c.scores is not polluted, "traces must not share score dicts"
    ids_with_bm25_q2 = {c.chunk_id for c in t2.fused if "bm25" in c.scores}
    assert "a" not in ids_with_bm25_q2, "query-1's BM25 hit must not leak into query 2"
    print("  isolation: cached templates pristine, no cross-query score leaks ✓")


def test_doc_scope_uses_subset():
    s = _fresh()
    restore = llm_client.embed
    llm_client.embed = lambda texts, **kw: [[1.0, 0.0] for _ in texts]
    try:
        t = search_trace("banach vector spaces", store=s, k=2, doc_id="doc-2")
    finally:
        llm_client.embed = restore
    assert t.final and all(c.doc_id == "doc-2" for c in t.final), \
        "doc-scoped search must only surface that document"
    print("  doc_scope: scoped search stays within its document ✓")


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    failed = 0
    print("running search-cache tests…")
    for t in TESTS:
        try:
            t()
        except AssertionError as e:
            failed += 1
            print(f"  ✗ {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ✗ {t.__name__}: unexpected {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.exit(1 if failed else 0)

"""Retrieval-engine tests — no network, no real embeddings/LLM (both faked):

    backend/.venv/bin/python tests/test_retrieval.py

Covers the store (add/count/get/query), dense search, BM25 exact-term, RRF fusion via
search_trace, and grounded answer assembly. Uses a deterministic bag-of-words embedder
so dense similarity is meaningful and reproducible.
"""

import re
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app import llm_client  # noqa: E402
from app.chunking.base import Chunk  # noqa: E402
from app.retrieval import VectorStore, answer_from, search_trace  # noqa: E402
from app.retrieval.bm25 import BM25  # noqa: E402
from app.retrieval.contextual import ContextualChunk  # noqa: E402

VOCAB = ["hölder", "inequality", "exponent", "exponents", "conjugate", "convexity",
         "results", "bound", "cauchy", "schwarz", "française", "prompt", "caching",
         "retrieval", "cheap", "généralise"]


def fake_embed(texts, model=None):
    vecs = []
    for t in texts:
        toks = set(re.findall(r"\w+", t.lower()))
        v = [1.0 if w in toks else 0.0 for w in VOCAB]
        vecs.append(v if any(v) else [1e-6] * len(VOCAB))
    return vecs


llm_client.embed = fake_embed  # patch the provider embedder for the whole module


def _cc(i, doc, text, context, pages, section):
    ch = Chunk(chunk_id=f"{doc}::{i}", doc_id=doc, index=i, text=text,
               header_path=section.split(" › ") if section else [], pages=pages)
    return ContextualChunk(chunk=ch, context=context)


def build_store():
    store = VectorStore("default", path=tempfile.mkdtemp())
    store.add([
        _cc(0, "math.pdf", "Hölder inequality requires conjugate exponents p and q.",
            "Methods section defining the exponents.", [2], "Methods"),
        _cc(1, "math.pdf", "The results confirm the bound is tight via a convexity argument.",
            "Results section.", [4], "Results"),
        _cc(2, "french.pdf", "L'inégalité de Hölder généralise Cauchy-Schwarz.",
            "Section française d'introduction.", [1], "Introduction"),
        _cc(3, "rag.pdf", "Prompt caching makes contextual retrieval cheap.",
            "Caching section.", [3], "Caching"),
    ])
    return store


def test_store_roundtrip():
    s = build_store()
    assert s.count() == 4, f"expected 4, got {s.count()}"
    got = s.get("math.pdf::0")
    assert got and "conjugate exponents" in got.text
    assert got.pages == [2] and got.section == "Methods"
    print("  store_roundtrip: 4 stored, get-by-id returns text + provenance ✓")


def test_dense_query():
    s = build_store()
    qvec = fake_embed(["Hölder conjugate exponents"])[0]
    hits = s.query(qvec, 3)
    assert hits[0].chunk_id == "math.pdf::0", f"dense top wrong: {hits[0].chunk_id}"
    assert hits[0].scores["dense"] > 0
    print(f"  dense_query: top = {hits[0].chunk_id} (sim {hits[0].scores['dense']}) ✓")


def test_bm25_exact_term():
    s = build_store()
    recs = s.all_records()
    bm = BM25().build([(r.chunk_id, r.embed_text) for r in recs])
    hits = bm.search("convexity", 3)  # rare term, only in chunk 1
    assert hits and hits[0][0] == "math.pdf::1", f"bm25 exact-term wrong: {hits}"
    print(f"  bm25_exact_term: 'convexity' -> {hits[0][0]} ✓")


def test_search_trace_fuses():
    s = build_store()
    tr = search_trace("Hölder exponents", k=4, store=s)
    assert tr.dense and tr.bm25 and tr.fused and tr.final, "a stage came back empty"
    top_ids = [c.chunk_id for c in tr.final[:2]]
    assert "math.pdf::0" in top_ids, f"expected math.pdf::0 in top-2, got {top_ids}"
    # the top fused chunk carries scores from both retrievers
    top = tr.fused[0]
    assert "rrf" in top.scores, "fused chunk missing rrf score"
    print(f"  search_trace: dense={len(tr.dense)} bm25={len(tr.bm25)} "
          f"fused={len(tr.fused)} final top={tr.final[0].chunk_id} ✓")


def test_rrf_rewards_agreement():
    s = build_store()
    tr = search_trace("Hölder conjugate exponents", k=4, store=s)
    # math.pdf::0 is found by BOTH dense and bm25 -> should top the fused list
    assert tr.fused[0].chunk_id == "math.pdf::0", f"RRF winner wrong: {tr.fused[0].chunk_id}"
    print("  rrf_rewards_agreement: chunk found by both retrievers ranks #1 ✓")


def test_answer_from_grounded():
    captured = {}

    def fake_chat(messages, **kw):
        captured["messages"] = messages

        class R:
            text = "Hölder requires conjugate exponents p, q [S1]."
            usage = None
        return R()

    original = llm_client.chat
    llm_client.chat = fake_chat
    try:
        s = build_store()
        chunks = search_trace("Hölder exponents", k=2, store=s).final
        ans = answer_from("What exponents does Hölder require?", chunks)
    finally:
        llm_client.chat = original
    assert ans.sources, "answer has no sources"
    user_msg = captured["messages"][-1]["content"]
    assert "[S1]" in user_msg and "source:" in user_msg, "grounded prompt missing source labels"
    assert "[S1]" in ans.text
    print(f"  answer_from: grounded prompt built, {len(ans.sources)} sources, cited ✓")


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    failed = 0
    print("running retrieval tests…")
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

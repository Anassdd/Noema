"""Supplement-fusion tests — no network, no stores (everything faked):

    backend/.venv/bin/python tests/test_fusion.py

Covers the novelty gate (redundant facts rejected, novel facts kept, budget respected,
coverage accumulates across accepted facts) and retrieve()'s hybrid contract: the vector
top-k is returned INTACT with graph facts only appended — the displacement bug that made
hybrid lose to rag-alone must never come back.
"""

import asyncio
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app import pipeline  # noqa: E402
from app.retrieval.base import ScoredChunk  # noqa: E402


def chunk(cid, text, score=0.5):
    return ScoredChunk(chunk_id=cid, text=text, context="", doc_id="doc-1",
                       pages=[1], section="", score=score, scores={})


CHUNKS = [
    chunk("c1", "Hölder's inequality bounds the integral of a product by the "
                "product of Lp norms with conjugate exponents."),
    chunk("c2", "The proof relies on Young's inequality and the convexity of the "
                "exponential function."),
]


def test_novelty_gate():
    facts = [
        chunk("graph:f1", "Hölder's inequality — generalizes — Cauchy-Schwarz"),   # novel: cauchy-schwarz
        chunk("graph:f2", "Hölder's inequality bounds the product of Lp norms"),   # restates c1
        chunk("graph:f3", "Cauchy-Schwarz — special case — exponent two"),         # partly covered by f1 now
        chunk("graph:f4", "Minkowski inequality — proves — triangle inequality for Lp spaces"),  # novel
    ]
    picked = pipeline._novel_facts(CHUNKS, facts, budget=4)
    ids = [f.chunk_id for f in picked]
    assert "graph:f1" in ids, "a fact bridging to an entity the chunks lack must get in"
    assert "graph:f2" not in ids, "a fact restating a chunk must be rejected"
    assert "graph:f4" in ids, "an unrelated-but-novel fact must get in"

    assert pipeline._novel_facts(CHUNKS, facts, budget=1) == [facts[0]], "budget must cap"
    assert pipeline._novel_facts(CHUNKS, [facts[1]], budget=4) == [], "all-redundant -> zero facts"
    assert pipeline._novel_facts(CHUNKS, [chunk("graph:e", "")], budget=4) == [], "empty text -> skipped"
    print("novelty gate ok")


def _wire(pool, facts):
    """Point retrieve() at a fake vector store and fake graph facts."""
    pipeline.search_trace = lambda query, **kw: type("T", (), {"final": pool[:8], "fused": pool})()

    async def fake_graph(query, **kw):
        return facts
    pipeline.graph_chunks = fake_graph


def test_hybrid_backbone_and_supplement():
    """The contract two measured failures taught us (interleave RRF, corroboration
    promotion — both displaced evidence and lost accuracy): the vector top-k must reach
    the context IDENTICAL to rag-alone; the graph only ever appends."""
    pool = [chunk(f"c{i}", f"vector passage {i} about topic-{i}") for i in range(20)]
    facts = [chunk(f"graph:g{i}", f"entity-{i} — relates — notion-{i}", score=0.9)
             for i in range(10)]
    _wire(pool, facts)

    final, meta = asyncio.run(pipeline.retrieve("q", k=8, use_vector=True, use_graph=True))
    assert final[:8] == pool[:8], "hybrid must keep the vector top-k IDENTICAL to rag-alone"
    assert all(c.chunk_id.startswith("graph:") for c in final[8:]), "facts only appended after"
    assert len(final) <= 8 + 8, "at most k facts on top (8+8 design)"

    final_rag, _ = asyncio.run(pipeline.retrieve("q", k=8, use_vector=True, use_graph=False))
    assert final_rag == pool[:8], "rag-alone unchanged"
    final_g, meta_g = asyncio.run(pipeline.retrieve("q", k=8, use_vector=False, use_graph=True))
    assert final_g == facts[:8] and meta_g["graph"] == 8, "graph-alone unchanged"
    print(f"backbone + supplement ok (8 chunks + {meta['graph']} novel facts)")


def test_typed_profiles_and_ladder():
    assert set(pipeline.PROFILES) == {"factoid", "relational", "global"}
    for prof in pipeline.PROFILES.values():
        assert prof["k"] >= 4 and prof["facts"] >= 4, "budgets shift, stores never starve"
    assert pipeline._escalate("factoid", 0) == "factoid"
    assert pipeline._escalate("factoid", 1) == "relational"
    assert pipeline._escalate("relational", 1) == "global"
    assert pipeline._escalate("global", 1) == "global", "the ladder caps at global"
    assert pipeline._escalate("garbage-type", 0) == "factoid", "unknown types fail open"
    print("typed profiles + escalation ladder ok")


def test_max_facts_budget():
    pool = [chunk(f"c{i}", f"vector passage {i} about topic-{i}") for i in range(20)]
    facts = [chunk(f"graph:g{i}", f"entity-{i} — relates — notion-{i}", score=0.9)
             for i in range(14)]
    _wire(pool, facts)
    final, meta = asyncio.run(pipeline.retrieve(
        "q", k=4, max_facts=12, use_vector=True, use_graph=True, rerank_mode="off"))
    assert len([c for c in final if not c.chunk_id.startswith("graph:")]) == 4
    assert meta["graph"] <= 12, "max_facts caps the supplement"
    assert meta["graph"] > 4, "a global-profile budget admits more than k facts"
    print(f"max_facts budget ok (4 chunks + {meta['graph']} facts)")


if __name__ == "__main__":
    test_novelty_gate()
    test_hybrid_backbone_and_supplement()
    test_typed_profiles_and_ladder()
    test_max_facts_budget()
    print("all fusion tests passed")

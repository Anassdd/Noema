"""Graphiti graph-layer edge-case tests — runnable on the graph venv:

    backend/.venv/bin/python tests/test_graph.py

These make REAL LLM calls (entity/edge extraction) so they cost a little and aren't
bit-for-bit deterministic. Two kinds of check therefore:
  - hard asserts on structural invariants that do NOT depend on the model
    (no crash, snapshot returns, edges carry provenance);
  - a verdict (win / partial / fail) on the behaviour we hope the model produces
    (a contradiction got invalidated, two mentions resolved to one node).

Every scenario saves its episodes + resulting graph snapshot + observations to
tests/results/graph_runs/<scenario>.json — those files are the "kept results" and
also feed the lab's replay view. Small graphs (2-3 episodes) keep cost down.
"""

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.config import settings  # noqa: E402
from app.graph import GraphMemory, graph_config  # noqa: E402

# The STRONG extractor (gpt-4o in dev). Graph quality depends on extraction quality —
# a weak model produces a sparse, low-value graph (CLAUDE.md), and notably misses the
# subject/relationship that temporal invalidation needs. Worth the few cents.
MODEL = settings.parse_model or settings.chat_model
RUNS = ROOT / "results" / "graph_runs"
RUNS.mkdir(parents=True, exist_ok=True)


def _dt(y, m, d):
    return datetime(y, m, d, tzinfo=timezone.utc)


def _save(name, description, episodes, snapshot, facts, observations, verdict):
    payload = {
        "scenario": name,
        "description": description,
        "model": MODEL,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "observations": observations,
        "episodes": [{"name": n, "body": b, "reference_time": t.isoformat()} for n, b, t in episodes],
        "facts": [f.to_dict() for f in facts],
        "snapshot": snapshot.to_dict(),
    }
    (RUNS / f"{name}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


async def _fresh(domain):
    mem = GraphMemory(domain, extract_model=MODEL)
    await mem.build()
    await mem.reset()        # clean slate across re-runs
    return mem


async def _ingest(mem, episodes):
    for name, body, t in episodes:
        await mem.add_episode(body, name=name, reference_time=t, source_description="test")


def _badge(v):
    return {"win": "✓", "partial": "≈", "fail": "✗"}.get(v, "?")


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------
async def _temporal_invalidation():
    name = "temporal_invalidation"
    episodes = [
        ("adidas", "Kendra Walsh's favorite shoe brand is Adidas. She wears Adidas every day.",
         _dt(2026, 1, 3)),
        ("nike", "Kendra Walsh's favorite shoe brand is now Nike. She no longer likes Adidas.",
         _dt(2026, 8, 21)),
    ]
    mem = await _fresh("test_temporal")
    await _ingest(mem, episodes)
    snap = await mem.snapshot()
    facts = await mem.search("What does Kendra like?")
    await mem.close()

    assert snap.nodes, "no entities were extracted at all"  # hard
    blob = [e.fact.lower() for e in snap.edges]
    invalidated = [e for e in snap.edges if not e.is_current]
    adidas_dead = any(("adidas" in e.fact.lower()) and not e.is_current for e in snap.edges)
    nike_live = any(("nike" in e.fact.lower()) and e.is_current for e in snap.edges)
    obs = [f"{len(snap.edges)} facts, {len(invalidated)} invalidated",
           f"adidas fact invalidated: {adidas_dead}", f"nike fact current: {nike_live}"]
    verdict = "win" if (adidas_dead and nike_live) else ("partial" if (invalidated or nike_live) else "fail")
    _save(name, "A contradicting later fact should invalidate (not delete) the old one.",
          episodes, snap, facts, obs, verdict)
    return name, verdict, obs


async def _entity_resolution():
    name = "entity_resolution"
    episodes = [
        ("intro", "Acme Corporation released a language model called Lumen.", _dt(2026, 2, 1)),
        ("again", "Acme builds reliable developer tools that engineers trust.", _dt(2026, 2, 2)),
    ]
    mem = await _fresh("test_resolution")
    await _ingest(mem, episodes)
    snap = await mem.snapshot()
    await mem.close()

    assert snap.nodes, "no entities extracted"  # hard
    acme_nodes = [n for n in snap.nodes if "acme" in n.name.lower()]
    obs = [f"{len(snap.nodes)} nodes total", f"{len(acme_nodes)} node(s) match 'acme'",
           "names: " + ", ".join(n.name for n in snap.nodes)]
    verdict = "win" if len(acme_nodes) == 1 else ("partial" if len(acme_nodes) else "fail")
    _save(name, "Two mentions of the same entity should resolve to ONE node, not duplicate.",
          episodes, snap, [], obs, verdict)
    return name, verdict, obs


async def _provenance():
    name = "provenance"
    episodes = [
        ("p1", "Marie Curie discovered radium in Paris.", _dt(2026, 3, 1)),
    ]
    mem = await _fresh("test_provenance")
    await _ingest(mem, episodes)
    snap = await mem.snapshot()
    facts = await mem.search("Who discovered radium?")
    await mem.close()

    assert snap.nodes, "no entities extracted"  # hard
    with_prov = [f for f in facts if f.episodes]
    obs = [f"{len(facts)} facts retrieved", f"{len(with_prov)} carry source episode(s)"]
    verdict = "win" if (facts and len(with_prov) == len(facts)) else ("partial" if with_prov else "fail")
    _save(name, "Every retrieved fact must trace back to its source episode (citable).",
          episodes, snap, facts, obs, verdict)
    return name, verdict, obs


async def _multi_hop():
    name = "multi_hop"
    episodes = [
        ("founder", "Dana Reeves founded Acme.", _dt(2026, 4, 1)),
        ("product", "Acme builds the Lumen language model.", _dt(2026, 4, 2)),
    ]
    mem = await _fresh("test_multihop")
    await _ingest(mem, episodes)
    snap = await mem.snapshot()
    facts = await mem.search("What does Dana Reeves' company build?")
    await mem.close()

    assert snap.nodes, "no entities extracted"  # hard
    bridged = any("lumen" in f.fact.lower() for f in facts)
    obs = [f"{len(facts)} facts retrieved",
           "top fact: " + (facts[0].fact[:80] if facts else "(none)"),
           f"surfaced 'Lumen' across the hop: {bridged}"]
    verdict = "win" if bridged else ("partial" if facts else "fail")
    _save(name, "A 2-hop question (Dana→Acme→Lumen) should surface the bridged fact.",
          episodes, snap, facts, obs, verdict)
    return name, verdict, obs


async def _incremental():
    name = "incremental"
    e1 = [("c1", "Paris is the capital of France.", _dt(2026, 5, 1))]
    e2 = [("c2", "Berlin is the capital of Germany.", _dt(2026, 5, 2))]  # clearly new entities
    mem = await _fresh("test_incremental")
    await _ingest(mem, e1)
    n1 = len((await mem.snapshot()).nodes)
    await _ingest(mem, e2)            # add without rebuild
    snap = await mem.snapshot()
    await mem.close()

    n2 = len(snap.nodes)
    assert n2 >= 1, "no entities after incremental add"  # hard
    obs = [f"nodes after 1st episode: {n1}", f"nodes after 2nd episode: {n2}",
           "graph grew without a rebuild" if n2 > n1 else "graph did not grow"]
    verdict = "win" if n2 > n1 else "partial"
    _save(name, "Adding a document extends the graph incrementally (no full rebuild).",
          e1 + e2, snap, [], obs, verdict)
    return name, verdict, obs


async def _empty_episode():
    name = "empty_episode"
    episodes = [("blank", "ok.", _dt(2026, 6, 1))]
    mem = await _fresh("test_empty")
    await _ingest(mem, episodes)     # must not crash on a contentless episode
    snap = await mem.snapshot()
    await mem.close()
    obs = [f"no crash on a contentless episode", f"{len(snap.nodes)} nodes extracted (expected ~0)"]
    verdict = "win"
    _save(name, "A contentless episode must not crash ingestion.",
          episodes, snap, [], obs, verdict)
    return name, verdict, obs


SCENARIOS = [_temporal_invalidation, _entity_resolution, _provenance,
             _multi_hop, _incremental, _empty_episode]


def main():
    print(f"running graph edge-case scenarios (model={MODEL}, backend={graph_config.backend})…\n")
    failed, results = 0, []
    for scen in SCENARIOS:
        try:
            name, verdict, obs = asyncio.run(scen())
            results.append((name, verdict))
            print(f"  {_badge(verdict)} {name}: {verdict}")
            for o in obs:
                print(f"        · {o}")
        except Exception as exc:  # a real (structural) failure, not LLM variance
            failed += 1
            print(f"  ✗ {scen.__name__}: CRASHED — {type(exc).__name__}: {exc}")
    wins = sum(v == "win" for _, v in results)
    print(f"\n{wins}/{len(SCENARIOS)} clean wins · {failed} crashes · results saved to "
          f"{RUNS.relative_to(ROOT.parent)}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

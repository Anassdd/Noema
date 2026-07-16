"""Graph-layer unit tests — no network, no FalkorDB, no LLM (everything stubbed):

    backend/.venv/bin/python tests/test_graph_units.py

Covers the audit fixes: the cross-encoder is built from OUR provider config (not
Graphiti's silent api.openai.com default); archived facts never eat result slots;
the search recipe dispatch (rrf = the exact legacy call, cross_encoder/mmr via
search_() on a copy, unknown = explicit error); and instructions_for() keeping the
induced-schema prefix on both the document and memory flavors.
"""

import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

os.environ.pop("OPENAI_API_KEY", None)  # prove nothing falls back to the env default

from app.config import settings  # noqa: E402
from app.graph import store as graph_store  # noqa: E402
from app.graph.config import GraphConfig  # noqa: E402
from app.graph.providers import build_cross_encoder  # noqa: E402
from app.graph.schema import InducedSchema, TypeDef  # noqa: E402
from app.graph.store import (DEFAULT_EXTRACTION_INSTRUCTIONS,  # noqa: E402
                             DOCUMENT_EXTRACTION_INSTRUCTIONS, GraphMemory)


def _edge(uuid):
    return SimpleNamespace(uuid=uuid, fact=f"fact {uuid}", name="RELATES",
                           source_node_uuid="s", target_node_uuid="t",
                           valid_at=None, invalid_at=None, created_at=None,
                           expired_at=None, episodes=[], score=0.5)


def _stub_mem(recipe="rrf", archived=(), n_edges=12):
    """A GraphMemory whose collaborators are all fakes — __init__ never runs."""
    mem = GraphMemory.__new__(GraphMemory)
    mem.config = GraphConfig(search_recipe=recipe)
    mem.group_id = "g"
    calls = {}

    async def fake_search(query, group_ids=None, num_results=10):
        calls["mode"], calls["asked"] = "search", num_results
        return [_edge(f"e{i}") for i in range(min(num_results, n_edges))]

    async def fake_search_(query, config=None, group_ids=None):
        calls["mode"], calls["asked"], calls["config"] = "search_", config.limit, config
        return SimpleNamespace(edges=[_edge(f"e{i}") for i in range(min(config.limit, n_edges))])

    mem.graphiti = SimpleNamespace(search=fake_search, search_=fake_search_)

    async def fake_archived():
        return set(archived)

    async def fake_names():
        return {}

    mem._archived_uuids = fake_archived
    mem._node_names = fake_names
    return mem, calls


def test_cross_encoder_is_provider_pinned():
    ce = build_cross_encoder()
    assert ce.config.api_key, "must never rely on the OPENAI_API_KEY env default"
    assert ce.config.model == settings.chat_model, "rerank model must come from settings"
    assert (ce.config.base_url or "") == (settings.base_url or ""), "base_url must follow the provider"
    print("  cross_encoder: built from provider config, no env fallback ✓")


def test_archived_never_eat_slots():
    archived = {"e0", "e2", "e4"}
    mem, calls = _stub_mem(archived=archived)
    facts = asyncio.run(mem.search("q", limit=5))
    assert calls["asked"] == 5 + len(archived), "fetch must widen by the archived count"
    assert len(facts) == 5, f"expected a full page of live facts, got {len(facts)}"
    assert not {f.uuid for f in facts} & archived, "archived facts must be filtered"
    print("  archived: over-fetched and filtered — full page of live facts ✓")


def test_overfetch_is_capped():
    mem, calls = _stub_mem(archived={f"a{i}" for i in range(100)})
    asyncio.run(mem.search("q", limit=5))
    assert calls["asked"] == 15, "over-fetch must cap at 3x limit"
    print("  overfetch_cap: 100 archived -> fetch capped at 3× limit ✓")


def test_recipe_rrf_uses_legacy_call():
    mem, calls = _stub_mem(recipe="rrf")
    facts = asyncio.run(mem.search("q", limit=4))
    assert calls["mode"] == "search" and len(facts) == 4
    print("  recipe_rrf: exact legacy graphiti.search() path ✓")


def test_recipe_cross_encoder_uses_search_():
    from graphiti_core.search.search_config_recipes import EDGE_HYBRID_SEARCH_CROSS_ENCODER
    mem, calls = _stub_mem(recipe="cross_encoder")
    facts = asyncio.run(mem.search("q", limit=4))
    assert calls["mode"] == "search_" and len(facts) == 4
    cfg = calls["config"]
    assert cfg is not EDGE_HYBRID_SEARCH_CROSS_ENCODER, "must run on a copy, never the shared singleton"
    assert cfg.edge_config.reranker == EDGE_HYBRID_SEARCH_CROSS_ENCODER.edge_config.reranker
    assert EDGE_HYBRID_SEARCH_CROSS_ENCODER.limit != 4, "the shared recipe must stay untouched"
    print("  recipe_cross_encoder: search_() on a private copy, singleton untouched ✓")


def test_recipe_unknown_raises():
    mem, _ = _stub_mem(recipe="fancy")
    try:
        asyncio.run(mem.search("q", limit=3))
    except ValueError as e:
        assert "GRAPH_SEARCH_RECIPE" in str(e)
        print("  recipe_unknown: explicit ValueError, no silent fallback ✓")
        return
    raise AssertionError("unknown recipe must raise, not silently degrade")


def test_instructions_for_keeps_schema_prefix():
    mem = GraphMemory.__new__(GraphMemory)
    mem._base_instructions = DEFAULT_EXTRACTION_INSTRUCTIONS
    mem.schema = None
    assert mem.instructions_for("memory") == DEFAULT_EXTRACTION_INSTRUCTIONS
    assert mem.instructions_for("document") == DOCUMENT_EXTRACTION_INSTRUCTIONS
    assert "pizza" not in DOCUMENT_EXTRACTION_INSTRUCTIONS

    mem.schema = InducedSchema(domain="basel", entity_types=[TypeDef("CapitalRequirement")],
                               edge_types=[TypeDef("APPLIES_TO")])
    doc = mem.instructions_for("document")
    memo = mem.instructions_for("memory")
    assert "basel" in doc and doc.endswith(DOCUMENT_EXTRACTION_INSTRUCTIONS), \
        "document flavor must keep the induced-schema prefix"
    assert "basel" in memo and memo.endswith(DEFAULT_EXTRACTION_INSTRUCTIONS), \
        "memory flavor must keep the induced-schema prefix"
    print("  instructions: both flavors compose with the induced schema ✓")


def test_fingerprint_reflects_new_extraction():
    from app.bench.runner import _EP_VERSION, _fingerprint
    assert _EP_VERSION != "ep700-v1", "EP version must be bumped with the new extraction prompt"
    a = _fingerprint("hash", 100, "m")
    assert graph_store  # silence unused-import linters
    assert len(a) == 10
    print(f"  fingerprint: EP version bumped to {_EP_VERSION} — old builds can't be reused ✓")


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    failed = 0
    print("running graph unit tests…")
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

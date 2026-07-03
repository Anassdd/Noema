"""Dream — one self-maintenance cycle over a domain's graph memory.

The graph already evolves on insert (Graphiti extracts, resolves entities against
existing ones and invalidates contradicted facts). Dream adds the passes that do
NOT happen on insert:

  dedupe      merge duplicate entities that split over time ("BNPP" vs "BNP Paribas")
  forget      archive long-superseded facts out of active retrieval; prune orphan nodes
  consolidate refresh community summaries (Graphiti's build_communities)

Safety over cleverness: episodes are never touched (append-only source of truth),
archival flags instead of deleting (history stays visible in snapshots), and every
pass runs against a GRAPH.COPY checkpoint — sanity-checked after, rolled back if it
lost knowledge. One attempt per pass, never a retry loop.
"""

from __future__ import annotations

import asyncio
import difflib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

from app import llm_client
from app.graph.base import GraphSnapshot
from app.graph.config import graph_config
from app.graph.manager import graph_manager
from app.graph.server import copy_graph, drop_graph
from app.graph.store import GraphMemory

GRACE_DAYS = int(os.getenv("DREAM_GRACE_DAYS", "7"))
# Off by default: graphiti 0.29.2's build_communities spun at 100% CPU indefinitely on
# our FalkorDB setup (6-node graph, no progress). Re-test on library upgrades before
# enabling — dedupe + forget are the load-bearing anti-explosion passes either way.
COMMUNITIES_ENABLED = os.getenv("DREAM_COMMUNITIES", "") == "1"
MIN_NODES_FOR_COMMUNITIES = 12
FUZZY_THRESHOLD = 0.84
MAX_PROBES = 3

_SAME_ENTITY_SYS = (
    "You judge whether two names from a knowledge graph refer to the SAME real-world "
    "entity (an alias, abbreviation, or spelling variant — e.g. 'BNP Paribas SA' and "
    "'BNPP'). Different things that merely sound alike are NOT the same. Reply ONLY "
    'with JSON: {"same": [true or false for each numbered pair, in order]}'
)


@dataclass
class PlannedPass:
    key: str
    reason: str


def _checkpoint_name(domain: str) -> str:
    return f"__dream_checkpoint__{domain}"




async def _query(mem: GraphMemory, cypher: str, **params) -> list[dict]:
    res = await mem._driver.execute_query(cypher, **params)
    records = res[0] if isinstance(res, tuple) else res
    return records or []


# ---- analyze ----------------------------------------------------------------
def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def _duplicate_candidates(snap: GraphSnapshot) -> tuple[list[list], list[tuple]]:
    """Exact groups (same normalized name → merge outright) and fuzzy pairs
    (similar names → need an LLM to confirm)."""
    by_norm: dict[str, list] = {}
    for n in snap.nodes:
        by_norm.setdefault(_normalize(n.name), []).append(n)
    exact = [same for same in by_norm.values() if len(same) > 1]

    reps = [(norm, nodes[0]) for norm, nodes in by_norm.items() if norm]
    fuzzy = []
    for i, (norm_a, a) in enumerate(reps):
        for norm_b, b in reps[i + 1 :]:
            if _similar_names(norm_a, norm_b):
                fuzzy.append((a, b))
    return exact, fuzzy


def _similar_names(norm_a: str, norm_b: str) -> bool:
    """Candidate duplicates: near-identical spellings, or one name compacting to a
    prefix of the other ('bnpp' / 'bnp paribas'). Generous on purpose — every
    candidate still has to pass the LLM same-entity check before any merge."""
    if difflib.SequenceMatcher(None, norm_a, norm_b).ratio() >= FUZZY_THRESHOLD:
        return True
    compact_a, compact_b = norm_a.replace(" ", ""), norm_b.replace(" ", "")
    if min(len(compact_a), len(compact_b)) < 3:
        return False
    return compact_a.startswith(compact_b) or compact_b.startswith(compact_a)


async def _stale_count(mem: GraphMemory, cutoff: str) -> int:
    rows = await _query(
        mem,
        "MATCH ()-[r:RELATES_TO]->() WHERE r.group_id = $g AND r.archived IS NULL "
        "AND (r.expired_at IS NOT NULL OR r.invalid_at IS NOT NULL) "
        "AND coalesce(r.expired_at, r.invalid_at) < $cutoff RETURN count(r) AS n",
        g=mem.group_id, cutoff=cutoff,
    )
    return rows[0]["n"] if rows else 0


async def _orphan_uuids(mem: GraphMemory) -> list[str]:
    """Entities with no fact edges at all — read straight from Cypher, never from a
    snapshot parse (a silent read failure must not make everything look orphaned)."""
    rows = await _query(
        mem,
        "MATCH (n:Entity) WHERE n.group_id = $g AND NOT (n)-[:RELATES_TO]-() "
        "RETURN n.uuid AS uuid",
        g=mem.group_id,
    )
    return [row["uuid"] for row in rows]


def _grace_cutoff() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=GRACE_DAYS)).isoformat()


async def _plan(mem: GraphMemory, snap: GraphSnapshot) -> list[PlannedPass]:
    passes = []
    exact, fuzzy = _duplicate_candidates(snap)
    if exact or fuzzy:
        passes.append(PlannedPass(
            "dedupe", f"{len(exact)} exact + {len(fuzzy)} likely duplicate entities"))
    stale = await _stale_count(mem, _grace_cutoff())
    orphans = len(await _orphan_uuids(mem))
    if stale or orphans:
        passes.append(PlannedPass(
            "forget", f"{stale} stale superseded facts, {orphans} orphan entities"))
    if COMMUNITIES_ENABLED and len(snap.nodes) >= MIN_NODES_FOR_COMMUNITIES:
        passes.append(PlannedPass(
            "consolidate", f"{len(snap.nodes)} entities → refresh community summaries"))
    return passes


# ---- pass: dedupe -----------------------------------------------------------
def _confirm_same(pairs: list[tuple]) -> list[bool]:
    """One batched LLM call over all fuzzy pairs. Fail-open to 'not same'."""
    lines = [
        f"{i + 1}. '{a.name}' ({a.summary[:120]}) vs '{b.name}' ({b.summary[:120]})"
        for i, (a, b) in enumerate(pairs)
    ]
    try:
        res = llm_client.chat(
            [{"role": "system", "content": _SAME_ENTITY_SYS},
             {"role": "user", "content": "\n".join(lines)}],
            temperature=0.0, max_tokens=200,
        )
        txt = res.text or ""
        verdicts = json.loads(txt[txt.index("{"): txt.rindex("}") + 1]).get("same", [])
        return [bool(v) for v in verdicts[: len(pairs)]] + [False] * (len(pairs) - len(verdicts))
    except Exception:
        return [False] * len(pairs)


def _pick_survivor(group: list, degree: dict) -> tuple:
    ranked = sorted(group, key=lambda n: (degree.get(n.uuid, 0), len(n.summary)), reverse=True)
    return ranked[0], ranked[1:]


async def _copy_edge(mem: GraphMemory, src: str, dst: str, props: dict) -> None:
    """Recreate a fact edge with its full properties. The embedding must round-trip
    through vecf32() — written as a plain list it corrupts FalkorDB's vector type
    and breaks vector search (caught by the post-pass probe the first time)."""
    props = dict(props)
    embedding = props.pop("fact_embedding", None)
    set_embedding = ", r.fact_embedding = vecf32($emb)" if embedding is not None else ""
    await _query(
        mem,
        "MATCH (a:Entity {uuid: $src}), (b:Entity {uuid: $dst}) "
        f"CREATE (a)-[r:RELATES_TO]->(b) SET r = $props{set_embedding}",
        src=src, dst=dst, props=props, emb=embedding,
    )


async def _merge_node(mem: GraphMemory, survivor, dup) -> None:
    """Repoint every edge from the duplicate onto the survivor (facts keep their
    uuid and properties — provenance intact), then remove the duplicate node."""
    outgoing = await _query(
        mem,
        "MATCH (d:Entity {uuid: $d})-[r:RELATES_TO]->(t:Entity) "
        "RETURN properties(r) AS props, t.uuid AS other",
        d=dup.uuid,
    )
    for row in outgoing:
        other = row["other"] if row["other"] != dup.uuid else survivor.uuid
        await _copy_edge(mem, survivor.uuid, other, row["props"])
    incoming = await _query(
        mem,
        "MATCH (o:Entity)-[r:RELATES_TO]->(d:Entity {uuid: $d}) "
        "RETURN properties(r) AS props, o.uuid AS other",
        d=dup.uuid,
    )
    for row in incoming:
        other = row["other"] if row["other"] != dup.uuid else survivor.uuid
        await _copy_edge(mem, other, survivor.uuid, row["props"])
    mentions = await _query(
        mem,
        "MATCH (ep:Episodic)-[m:MENTIONS]->(d:Entity {uuid: $d}) "
        "RETURN properties(m) AS props, ep.uuid AS ep",
        d=dup.uuid,
    )
    for row in mentions:
        await _query(
            mem,
            "MATCH (ep:Episodic {uuid: $ep}), (s:Entity {uuid: $s}) "
            "CREATE (ep)-[m:MENTIONS]->(s) SET m = $props",
            ep=row["ep"], s=survivor.uuid, props=row["props"],
        )
    await _query(mem, "MATCH (d:Entity {uuid: $d}) DETACH DELETE d", d=dup.uuid)

    alias = f"{survivor.summary} Also known as: {dup.name}.".strip()
    await _query(
        mem, "MATCH (s:Entity {uuid: $s}) SET s.summary = $summary",
        s=survivor.uuid, summary=alias[:2000],
    )


async def _run_dedupe(mem: GraphMemory, snap: GraphSnapshot) -> dict:
    exact, fuzzy = _duplicate_candidates(snap)
    if fuzzy:
        verdicts = await asyncio.to_thread(_confirm_same, fuzzy)
        for (a, b), same in zip(fuzzy, verdicts):
            if same:
                exact.append([a, b])

    degree: dict[str, int] = {}
    for e in snap.edges:
        degree[e.source_uuid] = degree.get(e.source_uuid, 0) + 1
        degree[e.target_uuid] = degree.get(e.target_uuid, 0) + 1

    merged = []
    absorbed: set[str] = set()
    for group in exact:
        group = [n for n in group if n.uuid not in absorbed]
        if len(group) < 2:
            continue
        survivor, dups = _pick_survivor(group, degree)
        for dup in dups:
            await _merge_node(mem, survivor, dup)
            absorbed.add(dup.uuid)
            merged.append(f"{dup.name} → {survivor.name}")
    return {"merged": len(merged), "details": merged[:12]}


# ---- pass: forget -----------------------------------------------------------
async def _run_forget(mem: GraphMemory, snap: GraphSnapshot) -> dict:
    cutoff = _grace_cutoff()
    stale = await _query(
        mem,
        "MATCH ()-[r:RELATES_TO]->() WHERE r.group_id = $g AND r.archived IS NULL "
        "AND (r.expired_at IS NOT NULL OR r.invalid_at IS NOT NULL) "
        "AND coalesce(r.expired_at, r.invalid_at) < $cutoff "
        "SET r.archived = true RETURN count(r) AS n",
        g=mem.group_id, cutoff=cutoff,
    )
    archived = stale[0]["n"] if stale else 0

    orphans = await _orphan_uuids(mem)
    for u in orphans:
        await _query(mem, "MATCH (n:Entity {uuid: $u}) DETACH DELETE n", u=u)
    return {"archived": archived, "pruned_orphans": len(orphans)}


# ---- pass: consolidate ------------------------------------------------------
CONSOLIDATE_TIMEOUT_S = int(os.getenv("DREAM_CONSOLIDATE_TIMEOUT_S", "300"))


async def _run_consolidate(mem: GraphMemory, snap: GraphSnapshot) -> dict:
    # Bounded: a hung community build must fail the pass (→ rollback), not wedge Dream.
    nodes, _edges = await asyncio.wait_for(
        mem.graphiti.build_communities(group_ids=[mem.group_id]),
        timeout=CONSOLIDATE_TIMEOUT_S,
    )
    return {"communities": len(nodes)}


# ---- post-pass check (one shot, no retry loops) ------------------------------
async def _episode_count(mem: GraphMemory) -> int:
    rows = await _query(
        mem, "MATCH (e:Episodic) WHERE e.group_id = $g RETURN count(e) AS n", g=mem.group_id)
    return rows[0]["n"] if rows else 0


def _sample_probes(snap: GraphSnapshot) -> list[str]:
    facts = [e.fact for e in snap.edges if e.is_current and len(e.fact) > 15]
    return facts[:MAX_PROBES]


async def _check(mem: GraphMemory, before: GraphSnapshot, episodes_before: int,
                 probes: list[str], allowed_node_loss: int) -> tuple[bool, str]:
    """Did the pass lose knowledge? Episodes must survive, every current fact must
    survive (archival flags don't remove edges), node removals must not exceed what
    the pass claims it did, and retrieval must still answer."""
    if await _episode_count(mem) != episodes_before:
        return False, "episode count changed"
    try:
        after = await mem.snapshot()
    except Exception as exc:
        return False, f"graph unreadable after pass: {exc}"
    if len(after.edges) != await mem._edge_count():
        return False, "edge read inconsistent after pass"
    after_uuids = {e.uuid for e in after.edges}
    lost = [e for e in before.edges if e.is_current and e.uuid not in after_uuids]
    if lost:
        return False, f"{len(lost)} current facts lost"
    node_loss = len(before.nodes) - len(after.nodes)
    if node_loss > allowed_node_loss:
        return False, f"removed {node_loss} nodes but only {allowed_node_loss} accounted for"
    for probe in probes:
        try:
            if not await mem.search(probe, limit=8):
                return False, "retrieval probe came back empty"
        except Exception as exc:
            return False, f"retrieval probe failed: {exc}"
    return True, ""


# ---- the dream cycle ---------------------------------------------------------
_RUNNERS = {"dedupe": _run_dedupe, "forget": _run_forget, "consolidate": _run_consolidate}


async def dream(domain: str, model: str | None = None) -> AsyncIterator[dict]:
    if graph_config.backend not in ("falkor_local", "falkor_server"):
        yield {"phase": "error", "detail": "Dream needs a FalkorDB server backend."}
        return

    mem = await graph_manager.get(domain, model or "")
    try:
        snap = await mem.snapshot()
    except Exception as exc:
        yield {"phase": "error", "detail": f"Can't read the graph safely: {exc}"}
        return
    if len(snap.edges) != await mem._edge_count():
        yield {"phase": "error",
               "detail": "Graph read is inconsistent — refusing to self-maintain on a bad read."}
        return
    if not snap.nodes:
        yield {"phase": "done", "summary": {}, "detail": "The memory is empty."}
        return

    yield {"phase": "analyze", "nodes": len(snap.nodes), "edges": len(snap.edges)}
    passes = await _plan(mem, snap)
    yield {"phase": "plan",
           "passes": [{"key": p.key, "reason": p.reason} for p in passes]}
    if not passes:
        yield {"phase": "done", "summary": {}, "detail": "Nothing to improve."}
        return

    checkpoint = _checkpoint_name(domain)
    summary: dict[str, dict] = {}
    try:
        for planned in passes:
            await asyncio.to_thread(copy_graph, domain, checkpoint)
            yield {"phase": "pass_start", "pass": planned.key, "reason": planned.reason}

            before = await mem.snapshot()
            episodes_before = await _episode_count(mem)
            probes = _sample_probes(before)
            try:
                changes = await _RUNNERS[planned.key](mem, before)
                allowed = changes.get("merged", 0) + changes.get("pruned_orphans", 0)
                ok, why = await _check(mem, before, episodes_before, probes, allowed)
            except Exception as exc:  # noqa: BLE001 — a broken pass must roll back
                ok, why, changes = False, str(exc), {}

            if ok:
                summary[planned.key] = changes
                yield {"phase": "pass_done", "pass": planned.key, "changes": changes,
                       "snapshot": await mem.snapshot()}
            else:
                await asyncio.to_thread(copy_graph, checkpoint, domain)
                yield {"phase": "pass_rolled_back", "pass": planned.key, "why": why,
                       "snapshot": await mem.snapshot()}
    finally:
        await asyncio.to_thread(drop_graph, checkpoint)

    yield {"phase": "done", "summary": summary}

# GRAPH.md — the temporal knowledge-graph memory (Graphiti)

The graph memory: a **temporal knowledge graph** built from text with
[Graphiti](https://github.com/getzep/graphiti). It is a *second, parallel* memory
alongside the contextual vector base — same documents, a different lens — and it is
**fully wired into the product**: ingestion streams into it from the graph page, the
expert pipeline retrieves from it (fused with the vector base), and **Dream**
(`evolution.py`) self-maintains it.

Book chapters: [docs/06-graph-memory.md](../../../docs/06-graph-memory.md) (concepts +
gotchas) and [docs/07-dream-evolution.md](../../../docs/07-dream-evolution.md) (Dream).
This file is the code-level map.

---

## One venv (Python 3.12)

The whole project runs on a single **Python 3.12** venv at `backend/.venv`. graphiti-core
needs 3.12 (its dependency tree isn't ready for 3.14), so the project was consolidated onto
3.12 — the **contextual base and the graph share one process**, which is what makes the
hybrid base+graph chat possible.

---

## What it does

```
text (an "episode")
   │  add_episode()                       ← incremental, one set of LLM calls
   ▼
extract entities → resolve/dedup → extract facts (edges) → invalidate contradictions
   │
   ▼
a temporal graph:  (entity) —[fact, valid_at … invalid_at]→ (entity)
```

- **Entities** are resolved (deduplicated) — "Acme" and "Acme Corp" become one node.
- **Facts** are edges carrying **bi-temporal** validity: `valid_at`/`invalid_at` (true
  in the world) and `created_at`/`expired_at` (when we learned/superseded it).
- A contradicting later fact **invalidates** the old one — it is **not deleted**, so
  history stays queryable. This is the whole point of using Graphiti over a plain graph.
- **Search** is hybrid: semantic embedding + BM25 + graph traversal, fused — minus any
  facts Dream has **archived** (demoted out of active retrieval, still in snapshots).

See `../../../courses/graphiti.html` for the deep, interactive explainer.

---

## The pieces

| File | Role |
|---|---|
| `config.py` | `GraphConfig` — picks the backend from `.env` (`GRAPH_BACKEND`). Local bundled server by default, real server/Neo4j later, **no code change**. |
| `providers.py` | Builds Graphiti's LLM + embedder from `app.config.settings` — the single provider-abstraction source (OpenAI ↔ llmaas is a `.env` switch). |
| `schema.py` | **Domain-adaptive extraction.** `induce_schema(sample, domain)` derives this domain's entity/relationship types from a corpus sample (GraphRAG-auto-tuning style); persisted per domain and used to bound extraction. |
| `server.py` | Auto-runs the FalkorDB server bundled in falkordblite (no Docker, no install) for `falkor_local` — **plus** the raw admin helpers `falkor_ops` / `copy_graph` / `drop_graph` used by saves and Dream checkpoints. |
| `base.py` | `GraphFact`, `GraphNode`, `GraphEdge`, `GraphSnapshot` — small JSON-serializable shapes with `is_current`. |
| `store.py` | `GraphMemory` — `build / add_episode / search / snapshot / episode_names / reset / apply_schema`. One graph per `domain_id`; auto-loads its saved schema; `search` filters archived facts; `snapshot` refuses to mistake a failed edge-read for an empty graph. |
| `manager.py` | `graph_manager` — shared instance cache + per-domain write lock (used by the routers and the pipeline). |
| `evolution.py` | **Dream** — the gated self-maintenance cycle: analyze → plan → per-pass GRAPH.COPY checkpoint → dedupe / forget / (consolidate) → sanity-check → commit or roll back. One attempt per pass, no retry loops. |
| `viz.py` | `render_html(snapshot)` — static vis-network render (used by the lab; the product UI is the React 3D page). |

Related, one level up: `app/saves.py` owns whole-memory checkpoints (this graph via
`GRAPH.COPY` + the Chroma collection under the same key), and `app/pipeline.py` adapts
`GraphFact` → `ScoredChunk` so graph facts fuse and cite like text chunks.

---

## Backend swap

```bash
# default — bundled FalkorDB server auto-started on :6399, persists to falkor.rdb
GRAPH_BACKEND=falkor_local

# a real FalkorDB server (Docker) — REQUIRED on Windows (redislite is Unix-only)
GRAPH_BACKEND=falkor_server
FALKOR_HOST=127.0.0.1
FALKOR_PORT=6379

# or Neo4j
GRAPH_BACKEND=neo4j
NEO4J_URI=bolt://host:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=...

# avoid: falkor_embedded (in-process redislite) — flaky under concurrent writes
```

`GraphMemory` reads only the config; the swap touches nothing else.

---

## Dream in three lines (details: docs/07)

- **dedupe** — merge duplicate entities (exact/fuzzy/abbreviation candidates → ONE batched
  LLM same-entity confirmation → Cypher merge preserving provenance + alias note).
- **forget** — archive facts superseded for > `DREAM_GRACE_DAYS` (flag, filtered from
  search, kept in history) + prune zero-edge orphan nodes. Demote, never destroy.
- **safety** — per-pass checkpoint; episodes and current facts must survive, node loss must
  match the pass's own report, edge reads must stay consistent, retrieval probes must still
  answer — else automatic rollback. Consolidate (`build_communities`) is off by default
  (`DREAM_COMMUNITIES=1`) — the 0.29.2 build spun on FalkorDB.

---

## Run it

```bash
# the WORKBENCH — text or PDF → live graph → ask & update (3-pane, schema-induced)
backend/.venv/bin/python -m streamlit run tests/graph_workbench.py

# the simple lab — add facts, see the graph, ask questions
backend/.venv/bin/python -m streamlit run tests/graph_lab.py

# the edge-case suite — saves results to tests/results/graph_runs/*.json
backend/.venv/bin/python tests/test_graph.py
```

**Domain-adaptive extraction.** Graphiti's default extraction is too narrow (misses domain
things) or, fully open, too noisy. The first build of a domain **samples the source and
induces that domain's entity/relationship types** (`schema.py`), persists them, and bounds
all extraction with them — finance, legal, medical each get their own schema, derived once.
Schema-bounded extraction beats schema-free by ~10–20 F1 in the literature.

The edge-case suite makes **real LLM calls** (extraction), so it costs a little and is not
bit-for-bit deterministic — it hard-asserts structural invariants and records a *verdict*
on model-dependent behaviour. Edge cases covered: temporal invalidation · entity
resolution · provenance · multi-hop · incremental growth · contentless episode.

---

## Provider note (the one architectural exception)

CLAUDE.md says all model calls go through one module. Graphiti requires its own client
objects, so `providers.py` is the **single sanctioned place** the graph layer configures
models — and it reads `app.config.settings` and nothing else, so the provider switch stays
config-only, in spirit with the rule. Extraction defaults to the **strong** model (a weak
extractor yields a sparse, low-value graph).

---

## Gotchas (the ones that cost hours)

1. **`domain_id` vs `group_id`** — a save's graph is a raw copy keeping the BASE domain's
   `group_id`; connect to `domain_id`, filter by `base_group_id(domain_id)`.
2. **FalkorDriver binds to one event loop** — one `asyncio.run` per script; uvicorn is fine;
   FastAPI `TestClient` (loop per request) is not.
3. **Vector properties need `vecf32()`** — writing an embedding back as a plain list
   corrupts the `Vectorf32` type and silently breaks vector search (see
   `evolution._copy_edge`).
4. **Destructive decisions read ground truth via Cypher**, never via a snapshot parse that
   can fail silently (see `evolution._orphan_uuids`).

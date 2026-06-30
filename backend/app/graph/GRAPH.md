# GRAPH.md — the temporal knowledge-graph memory (Graphiti)

The graph memory: a **temporal knowledge graph** built from text with
[Graphiti](https://github.com/getzep/graphiti). It is a *second, parallel* memory
alongside the contextual vector base — same documents, a different lens — kept behind
a small surface so it can later slot in beside the base under one retrieval interface.

This is the **graph layer, standalone** — built and tested on its own *before* it's
wired into the chatbot. The seam to the chat (`ScoredChunk`) is a thin future adapter,
not built yet.

---

## One venv (Python 3.12)

The whole project now runs on a single **Python 3.12** venv at `backend/.venv`. graphiti-core
needs 3.12 (its dependency tree isn't ready for 3.14), so the project was consolidated onto
3.12 — meaning the **contextual base and the graph share one process** (no more split venv).
Everything runs with `backend/.venv/bin/python` (the app, tests, labs). This is what makes a
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
- A contradicting later fact **invalidates** the old one (sets `invalid_at`) — it is
  **not deleted**, so history stays queryable. This is the whole point of using
  Graphiti over a plain graph.
- **Search** is hybrid: semantic embedding + BM25 + graph traversal, fused.

See `../../../courses/graphiti.html` for the deep, interactive explainer.

---

## The pieces

| File | Role |
|---|---|
| `config.py` | `GraphConfig` — picks the backend from `.env` (`GRAPH_BACKEND`). Embedded now, server later, **no code change**. |
| `providers.py` | Builds Graphiti's LLM + embedder from `app.config.settings` — the single provider-abstraction source (OpenAI ↔ llmaas is a `.env` switch). |
| `schema.py` | **SOTA domain-adaptive extraction.** `induce_schema(sample, domain)` derives this domain's entity/relationship types from a corpus sample (GraphRAG-auto-tuning style); persisted per domain and used to bound extraction. |
| `server.py` | Auto-runs the FalkorDB server bundled in falkordblite (no Docker, no install) for the `falkor_local` backend. |
| `base.py` | `GraphFact`, `GraphNode`, `GraphEdge`, `GraphSnapshot` — small JSON-serializable shapes. |
| `store.py` | `GraphMemory` — `build / add_episode / search / snapshot / reset / apply_schema`. One graph per `domain_id`; auto-loads its saved schema. |
| `viz.py` | `render_html(snapshot)` — interactive vis-network graph (drag/zoom/hover; current facts green, invalidated dashed). |

---

## Backend swap (embedded → server)

Set in `.env`:

```bash
# default — in-process, no server, persists to tests/results/graph_store/<domain>.rdb
GRAPH_BACKEND=falkor_embedded

# later: a real FalkorDB server
GRAPH_BACKEND=falkor_server
FALKOR_HOST=...
FALKOR_PORT=6379

# or Neo4j
GRAPH_BACKEND=neo4j
NEO4J_URI=bolt://host:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=...
```

`GraphMemory` reads only the config; the swap touches nothing else.

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

**Domain-adaptive extraction (the SOTA approach).** Graphiti's default extraction is
too narrow (misses domain things) or, fully open, too noisy. Instead the first build of
a domain **samples the source and induces that domain's entity/relationship types**
(`schema.py`), persists them, and bounds all extraction with them — so finance, legal,
medical each get their own schema, derived once, no hand-crafting. This is the
GraphRAG-auto-tuning / AutoSchemaKG pattern; schema-bounded extraction beats schema-free
by ~10–20 F1 in the literature.

The edge-case suite makes **real LLM calls** (extraction), so it costs a little and is
not bit-for-bit deterministic — it hard-asserts the structural invariants (no crash,
snapshot returns, facts carry provenance) and records a *verdict* on model-dependent
behaviour (did the contradiction get invalidated, did two mentions resolve to one
node). The saved JSON doubles as the lab's offline replay data.

Edge cases covered: temporal invalidation · entity resolution · provenance ·
multi-hop · incremental growth · contentless episode.

---

## Provider note (the one architectural exception)

CLAUDE.md says all model calls go through one module. Graphiti requires its own client
objects, so `providers.py` is the **single sanctioned place** the graph layer
configures models — and it reads `app.config.settings` and nothing else, so the
provider switch stays config-only, in spirit with the rule. Extraction defaults to the
**strong** `parse_model` (a weak extractor yields a sparse, low-value graph); the lab
uses the cheap model for snappy play.

---

## Not yet (deliberately)

- **No chat wiring.** Connecting to the retrieval seam (`search()` → `ScoredChunk`) and
  the side-by-side comparison with the contextual base is the next phase.
- **No communities, no evolution loop.** Graphiti supports both (`build_communities`,
  invalidation is already on); the consolidation/eval-gate loop is Phase 2.
- **Ingest from parsed docs.** `add_episode` per page (with provenance) is a small add
  when we connect real corpus documents.

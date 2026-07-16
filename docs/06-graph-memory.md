# 06 — Graph memory

The temporal knowledge graph: what Graphiti gives us, how Noema wraps it, how saves and the
3D page work, and the gotchas that will bite you if you don't know them. Code deep-dive:
[backend/app/graph/GRAPH.md](../backend/app/graph/GRAPH.md).

## Why a *temporal* graph

A plain knowledge graph stores "the CEO is Alice". When Bob replaces her, you either
overwrite (history lost) or keep both (contradiction). Graphiti's model keeps **facts as
edges with a validity interval**: ingesting the new fact *invalidates* the old edge
(`invalid_at`/`expired_at` set, edge kept). So the graph can answer both "who is CEO now?"
and "who was CEO in 2022?", and the 3D page can scrub through time. This
invalidate-don't-delete behavior is the foundation Dream builds on.

## What happens on ingest (`GraphMemory.add_episode`)

Each page of a PDF (or pasted text) becomes one **episode** — the append-only source of
truth. Per episode, Graphiti runs LLM passes to:

1. **Extract** entities and relationship facts (guided by our extraction instructions).
2. **Resolve** each entity against existing nodes (dedup at insert time).
3. **Relate + invalidate** — new facts link in; contradicted old facts get invalidated.

This is why graph ingest is the slow, expensive path (~several LLM calls per page) and why
the upload endpoint streams per-page progress. Extraction quality depends on the model —
weak extractors produce sparse graphs (the config exposes `GRAPH_EXTRACT_MODEL`).

Extraction instructions come in two flavors (`GraphMemory.instructions_for(kind)`):
**document** — for corpus/PDF ingestion: domain concepts, standards with identifiers,
metrics with values, directional assertions (defines / requires / applies-to /
supersedes…) — used by the bench builder and the PDF upload; and **memory** — the
original broad flavor for conversational or pasted-note text (preferences, opinions,
everyday entities). Both compose with the induced schema when the domain has one.

### Induced schemas

`graph/schema.py` can sample a corpus and derive a domain-specific schema (entity/relation
types) that then *bounds* extraction — fewer junk node types, more consistent graphs.
Persisted per domain, applied automatically when present.

## The layer around Graphiti

| File | Role |
|---|---|
| `store.py` | `GraphMemory` — the whole public surface: `build`, `add_episode`, `search`, `snapshot`, `episode_names`, `reset`. One instance per domain. |
| `manager.py` | Shared cache of instances + a per-domain write lock (`graph_manager`). |
| `config.py` | `GRAPH_BACKEND` selection (see below). |
| `providers.py` | Builds Graphiti's LLM/embedder clients from the same `.env` settings as everything else — the provider seam extended to the graph. |
| `server.py` | Auto-starts the bundled FalkorDB server + raw admin helpers (`falkor_ops`, `copy_graph`, `drop_graph`) used by saves and Dream. |
| `evolution.py` | Dream — see [07](07-dream-evolution.md). |
| `schema.py` | Schema induction. |
| `viz.py` | Static HTML rendering (used by the lab; the product UI is the React 3D page). |

### Graph backends (`GRAPH_BACKEND`)

| Value | What it is | When |
|---|---|---|
| `falkor_local` *(default)* | the FalkorDB server binary bundled in `falkordblite`, auto-started on :6399, persists to `falkor.rdb` | Mac/Linux dev — zero setup |
| `falkor_server` | external FalkorDB (Docker) | **Windows** (redislite is Unix-only) and production |
| `falkor_embedded` | in-process redislite | avoid — flaky under Graphiti's concurrent writes |
| `neo4j` | Neo4j driver | if the company prefers Neo4j |

## Search, and how facts become citations

`GraphMemory.search()` runs Graphiti's hybrid fact search (semantic + BM25 + graph),
filtered to the domain's `group_id`, minus any facts Dream has **archived** (an
`archived` flag checked via `_archived_uuids()` — archived facts stay in snapshots but
leave active retrieval; the fetch is widened by the archived count, so a full page of
live facts always comes back). The recipe is selectable via `GRAPH_SEARCH_RECIPE`
(`rrf` default — the measured baseline; `cross_encoder` re-ranks facts with cheap LLM
calls; `mmr` diversifies) — flipping it is a bench experiment, not a code change.

Provenance: episodes are named `"<file> · p<N>"` at ingestion. A retrieved fact carries its
episode uuids; `episode_names()` maps them back, and the pipeline parses doc + page out of
the name — that's how a graph fact cites like a text chunk.

## Saves — whole-memory checkpoints

`app/saves.py` owns them. A save copies **both stores under one key**:
the FalkorDB graph via `GRAPH.COPY` → `__save__<domain>__<name>`, and the Chroma collection
via `copy_into()` under the same key. Restore overwrites the live domain from the copy;
delete drops both. The UI exposes this as the ⧉ Saves panel; the chat's memory selector
answers *from* a save without touching the live domain.

## The 3D page (`frontend/src/graph/`)

`?view=graph` lazy-loads a standalone React tree:

- **Rendering:** `3d-force-graph` (three.js). `graph3d.js` enriches the snapshot — Louvain
  community detection → node colors, degree → node size; a "topics" view collapses clusters.
- **Live growth:** PDF upload streams NDJSON (one event per extracted page) and the graph
  redraws as it grows; same pattern for Dream's per-pass events.
- **Time scrubber:** every edge carries its timestamps, so the page can replay the memory
  as of any moment — invalidated facts render differently (dashed) instead of vanishing.
- **Panels:** Saves and Beliefs (in `panels.jsx`), the ✦ Dream button, Reset, and the
  ingest controls (drop zone / paste box / model picker).

## Gotchas (hard-won — read before touching)

1. **`domain_id` vs `group_id`.** FalkorDB stores each graph under a name — for a save
   that's `__save__default__v1`. But the *data inside* keeps the base domain's `group_id`
   (`default`), because a save is a raw copy. `GraphMemory` therefore connects to
   `domain_id` but filters queries by `base_group_id(domain_id)`. Confusing these returns
   empty results from perfectly good saves.
2. **The FalkorDriver binds to one event loop.** Create `GraphMemory` on the loop that will
   use it. Under uvicorn everything lives on the app loop — fine. In scripts, do all work
   inside a single `asyncio.run(main())`. (This is why FastAPI's `TestClient`, which makes
   a fresh loop per request, breaks against the graph — test with a live uvicorn instead.)
3. **Never write embeddings back as plain lists.** FalkorDB stores vectors as `Vectorf32`;
   round-tripping edge properties through Cypher and writing them back without `vecf32()`
   corrupts the type and silently breaks vector search. `evolution._copy_edge` shows the
   correct pattern.
4. **Don't parse your way to destructive decisions.** `snapshot()` can fail to parse edges
   (e.g. a malformed property) — code that deletes things must read ground truth via
   direct Cypher (`_edge_count`, `_orphan_uuids`), never infer "empty" from a failed parse.
5. **`falkor_embedded` is not production-safe** — concurrent writes scatter across
   ephemeral processes. Use `falkor_local` or a real server.

## Costs

Graph ingest: ~3–6 LLM calls per page (extract, resolve, dedupe, summarize). Search: one
embedding + cheap DB work. Dream: one batched dedup-confirm call (plus per-community
summaries when the consolidate pass is enabled).

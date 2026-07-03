# Noema — Current State

A snapshot of what is **actually built** today. The detailed documentation lives in
[`docs/`](docs/01-overview.md) — this page is the one-screen version.

> Historical note: an earlier revision of this file described the Phase-1 chat shell,
> before the memory existed. Everything below reflects the current build.

## Built and working

- **Ingestion** (graph page): PDF → per-page vision parsing → *both* memories —
  contextual vector base (chunk → LLM blurb → Chroma + BM25) **and** Graphiti temporal
  knowledge graph (entities/facts with time validity, contradiction supersession) —
  streamed page-by-page into the 3D view. Incremental; no rebuilds.
- **Expert chat**: contextualize+route → retrieve from vector ⊕ graph, RRF-fused → CRAG
  sufficiency check → grounded answer with `[S1]` citations → Self-RAG faithfulness check,
  all streamed with a live reasoning trace. Any-language follow-up resolution.
- **Graph Memory page** (`?view=graph`): 3D force graph (Louvain-colored, degree-sized),
  live growth during ingest, time scrubber over fact validity, node/edge inspection.
- **Saves**: named checkpoints of the whole memory (graph + vector base together);
  restore/delete; the chat can answer *from* a save.
- **Beliefs**: the user's own notes per memory context (✎ panel or `/note` in chat, with
  reference-resolving cleanup) — injected apart from the corpus; disagreements are
  surfaced, both sides attributed.
- **✦ Dream**: one-button graph self-maintenance — merge duplicate entities (LLM-confirmed),
  archive long-superseded facts (demote-don't-destroy), prune orphan debris — each pass
  checkpointed, sanity-checked, rolled back on any knowledge loss.
- **Chat shell** (from Phase 1, still the daily surface): streaming SSE chat, durable
  conversations (SQLite), personas, slash commands (`/remember /note /character /forget
  /clear /help`), persistent user memory (Markdown + LLM judge), per-chat PDFs stuffed
  into context under a token budget, model picker, themes, token accounting.
- **Provider portability**: `LLM_PROVIDER=openai|llmaas` — dev key or corporate
  OpenAI-compatible endpoint, config-only switch. Windows deploy documented
  (Docker FalkorDB).
- **Testing**: a Streamlit lab (parser/chunker/contextualizer/retrieval inspectors with
  saved traces) + scripted suites for chunking, contextualization, text-layer routing,
  retrieval, and graph edge cases.

## Not built yet (deliberate — see [docs/11-roadmap.md](docs/11-roadmap.md))

- The **evaluation bench** (method comparison + the Dream eval gate) — next big piece.
- Automatic evolution triggers (Dream is manual by design for now).
- Additional memory methods behind the pluggable interface (LightRAG, HippoRAG…).
- Phase-3 multifield routing.
- CI, UI tests, multi-user.

## Stack

| Layer | Tech |
| --- | --- |
| Backend | Python 3.12, FastAPI, Pydantic; Chroma (vectors), FalkorDB via Graphiti (graph), SQLite (chats) |
| Frontend | React 19 + Vite + Tailwind v4; `3d-force-graph`/three.js for the graph page |
| LLM access | one provider-abstraction module (`app/llm_client.py`); OpenAI (dev) or any OpenAI-compatible `/v1` (prod) |

Start at [docs/01-overview.md](docs/01-overview.md) for the full architecture.

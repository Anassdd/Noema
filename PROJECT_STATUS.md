# Noema — Project Résumé & Status

*Snapshot: 2026-07-15*

**Noema is a domain-expert chatbot whose knowledge is an evolving memory built from your own
documents.** You upload PDFs (mainly research papers); Noema builds two synchronized memories
from them and answers questions in "expert mode" with citations back to the exact document
and page. The knowledge graph is visible and navigable in 3D, can be checkpointed, carries
your own notes, and can clean itself on demand.

---

## 1. The idea in one picture

```
   DOCUMENTS                    TWO SYNCHRONIZED MEMORIES                 GROUNDED CHAT
  ┌─────────┐      ┌──────────────────────────────────────┐      ┌────────────────────┐
  │  PDFs   │ ───▶ │  Contextual vector base (dense+BM25)  │ ───▶ │ route → retrieve   │
  │ (papers)│      │  Temporal knowledge graph (Graphiti)  │      │ → grade → answer   │
  └─────────┘      └──────────────────────────────────────┘      │ → verify, w/ [S#]  │
                     same chunks, two lenses, shared               └────────────────────┘
                     provenance (doc + page)
```

Everything runs through **one provider seam** (`llm_client.py`) so the same code works on a
personal OpenAI key (dev) or a corporate OpenAI-compatible endpoint (prod) — switching is a
`.env` change, never a code change.

---

## 2. What is built (Phase 1 — Monofield expert)

Phase 1 is **functionally complete end-to-end**: ingest → dual memory → grounded chat → 3D
graph → self-maintenance.

### Ingestion & parsing
- ✅ PDF → Markdown via a **vision LLM per page** (default parser, works everywhere);
  optional **Azure Document Intelligence** backend, selectable by `PARSER` env var.
- ✅ Multilingual (the corpus is largely French); legibility-aware handling of LaTeX PDFs.
- ✅ Structure-aware Markdown **chunker**.

### Memory #1 — Contextual vector base (`retrieval/`)
- ✅ Anthropic-style **Contextual Retrieval**: each chunk gets an LLM-written situating blurb
  before embedding.
- ✅ **Hybrid search**: dense embeddings (Chroma) ‖ BM25, fused with **RRF**, then **reranked**.
- ✅ Provenance kept to document + page for citations.

### Memory #2 — Temporal knowledge graph (`graph/`)
- ✅ **Graphiti** temporal graph: extracts entities → resolves/dedupes → extracts facts →
  **invalidates contradictions instead of deleting** (bi-temporal: `valid_at`/`invalid_at`).
- ✅ **Incremental** — adding a document extends the graph, no full rebuild; one episode per
  page with source names.
- ✅ Runs on **FalkorDB** (bundled local, or external server via `GRAPH_BACKEND`).

### Expert chat pipeline (`pipeline.py`)
- ✅ Agentic loop: **route → retrieve (vector ⊕ graph, RRF-fused) → grade evidence (CRAG) →
  answer with `[S#]` citations → verify faithfulness (Self-RAG)**, streamed with live status.
- ✅ **Query contextualization** — follow-ups ("what about him?") rewritten into standalone
  queries before retrieval, in any language.
- ✅ Answers weigh the user's **beliefs** against the sources and flag disagreement.

### The graph memory page (3D)
- ✅ Drop PDFs and watch the graph grow **page by page in 3D** (three.js / 3d-force-graph).
- ✅ **Time scrubber** to travel through the graph's history.
- ✅ **Saves** — named checkpoints of the *whole* memory (graph + vector base), restore anytime.
- ✅ **Beliefs** — your own notes per memory context, kept apart from the corpus.
- ✅ **Topics/communities** view (client-side Louvain coloring).
- ✅ **✦ Dream** — one-button self-maintenance: merge duplicate entities, archive stale facts;
  each pass checkpointed, sanity-checked, and **rolled back if it loses knowledge**.

### Multiple memory engines (pluggable)
- ✅ **Graphiti** and **LightRAG** both wired as interchangeable engines behind one interface;
  the graph page can switch between them, each keeps its own pre-built store.
- 💤 A dormant instant word co-occurrence graph (`textgraph/`) kept as a possible future lens.

### Chat product surface
- ✅ Streaming chat with conversations, personas, slash commands (`/remember`, `/note`,
  `/character`, `/forget`, `/clear`, `/help`), per-chat PDFs, persistent user memory.
- ✅ **Accounts / auth**: per-user private conversations, memory, and beliefs (added 2026-07-15).

### Evaluation bench
- ✅ **?view=bench** surface: prepare a corpus → approve gold questions → build **once** →
  compare **closed-book / RAG / graph / hybrid** over one shared build → fixed-schema report.
- ✅ Bench design frozen in `studies/NOEMA_EVAL_BENCH.md`.

### Provider abstraction (the critical architectural rule)
- ✅ All chat + embedding calls go through `llm_client.py` only.
- ✅ Providers: `openai` (dev) and `llmaas` (prod, OpenAI-compatible Azure-hosted `/v1`).
  Optional params conditionally included so newer models don't break.

### Docs & research
- ✅ Numbered developer book: `docs/01`–`docs/11`, plus deep-dives next to the code
  (`GRAPH.md`, `RETRIEVAL.md`, `CONTEXTUAL.md`, `PARSING.md`, `CHUNKING.md`).
- ✅ Interactive **Architecture Explorer** (`docs/architecture.html`) and several
  presentation decks (contextual RAG, Graphiti, Dream, bench).
- ✅ SOTA research reports in `studies/` (memory, parsing, evolution, UX).

---

## 3. Timeline (from git history)

| When | Milestone |
|---|---|
| 2026-06-16 | Functional base chatbot + conversation database |
| 2026-06-22 | PDF parsing via vision (Docling tried, dropped) |
| 2026-06-24 | Chunker + contextual retrieval (RAG) done |
| 2026-06-30 | Graphiti graph backend added; retrieval RAG complete |
| 2026-07-01 | Chatbot v1 + 3D graph visualization page |
| 2026-07-03 | Dreaming (self-maintenance) added; docs written; 150k-context PDFs |
| 2026-07-08–10 | Bench built & tested; **LightRAG** engine + per-engine saves |
| 2026-07-15 | Accounts/auth + per-user private data; knowledge stores refreshed |

---

## 4. What's next

**Phase 2 — Evolutive memory** *(foundation already shipped as the manual Dream button):*
- Automatic, eval-gated curation triggers so the memory stays bounded ("don't explode").
- Standardized evolution contract across all engines (spec in
  `studies/NOEMA_EVOLUTION_CONTRACT.md`).

**Phase 3 — Multifield + routing:**
- Several domain experts; a router that picks the right field, detects multi-field questions,
  and decides whether we're actually expert in it.

See `docs/11-roadmap.md` for the detailed roadmap and known limitations.

---

## 5. How to run (dev, macOS)

```bash
# Backend (port 8000) — Python 3.12
cd backend && python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # put your OPENAI_API_KEY in backend/.env
uvicorn app.main:app --reload

# Frontend (port 5173), separate terminal
cd frontend && npm install && npm run dev
```

- **Chat:** `http://localhost:5173/`
- **Graph memory:** `http://localhost:5173/?view=graph`
- **Bench:** `http://localhost:5173/?view=bench`

Windows / production: `RUN_ON_WINDOWS.md` (external FalkorDB + `llmaas` provider).

---

**Bottom line:** Phase 1 is a working, grounded, citation-backed expert over your own
documents, with a live 3D memory you can save, annotate, compare across engines, and let
self-maintain. The next frontier is making that memory evolve automatically and then span
multiple domains.

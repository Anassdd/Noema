# CLAUDE.md — Working Spec for Noema (Expert Chatbot)

Context for Claude Code working in this repo. Read it before generating code.
It describes the system as built, its invariants, and the working rules. The deep
documentation lives in `docs/01–11` (the book) and `studies/` (frozen design specs);
prefer those over re-deriving decisions.

## One-line summary

A domain-expert chatbot whose knowledge is an **evolving graph+vector memory** built
from uploaded documents, with grounded source-citing answers, a navigable 3D graph,
and a benchmark that compares memory methods head-to-head on the same corpus.

## What exists (Phase 1 complete, Phase 2 partial)

- **Backend:** Python + FastAPI (`backend/app/`). **Frontend:** React + Vite
  (`frontend/`) — chat, ingestion, `?view=graph` (3D Graphiti view + ✎ Beliefs),
  `?view=bench` (the eval bench). File-backed auth (accounts + guests, no DB —
  locked-down-machine constraint); conversations, memory and beliefs are per-user.
- **Retrieval strategies**, user-selectable per message (`retrieval=`), each with its
  own store per domain, checkpointable via saves (`app/saves.py`):
  - `rag` — contextual retrieval (`app/retrieval/`): 512-token structure-aware chunks
    → LLM situating blurb → embed + BM25 (both over blurb+chunk) → RRF → LLM rerank
    (`RETRIEVAL_RERANK`, default on). Query-side records+BM25 are cached per domain
    (`index_cache.py`) — never rebuild per query.
  - `graph` — Graphiti temporal KG on FalkorDB (`app/graph/`), episodes per page named
    `<file> · p<N>` so facts cite doc+page. Search recipe via `GRAPH_SEARCH_RECIPE`
    (default `rrf` — the measured baseline).
  - `hybrid` — **supplement fusion** (`app/pipeline.py`): the vector top-k reaches the
    context IDENTICAL to rag-alone; graph facts only append through a novelty gate.
    This contract is MEASURED (cross-store RRF and graph-promotion both lost badly on
    the bench) and locked by `tests/test_fusion.py` — do not re-litigate without a
    bench run.
  - `lightrag` — self-contained second engine (`app/lightrag/`), not fused.
- **Expert answer loop:** route (typed: factoid/relational/global, corpus-map-aware)
  → retrieve → CRAG sufficiency check → grounded answer with `[S#]` citations →
  Self-RAG groundedness check → escalating retry ladder.
- **Evolution (Phase 2):** Dream for Graphiti (`app/graph/evolution.py`, archival tier
  + eval gate); the cross-method contract is specced in
  `studies/NOEMA_EVOLUTION_CONTRACT.md`. Phase 3 (multi-field routing) not started.

## Provider abstraction (critical — unchanged)

- Providers are `openai` (dev Mac, personal key) and `llmaas` (prod: the company's
  OpenAI-compatible gateway at a custom base_url — the same SDK, NOT the AzureOpenAI
  SDK; that branch was removed deliberately).
- ALL chat/embedding calls go through `app/llm_client.py`, configured only by
  `app/config.py` from `.env`. The graph layer gets its Graphiti clients (LLM,
  embedder, cross-encoder) exclusively from `app/graph/providers.py`. The bench judge
  has its own seam (`JUDGE_*` env — a different model family than the generator).
  Nothing else may import an LLM SDK.
- Switching providers is a config change, never a code change. Include optional params
  conditionally (newer models reject unknown/legacy keys — don't pass nulls).
- **When changing the chat model, resize `CONTEXT_DOC_CAP` in `.env`.** The
  contextualizer sends the whole document per chunk only when it fits this cap;
  larger docs auto-switch to head+section excerpts. Keep the cap ≈20k tokens under
  the model's usable input (250000 fits the GPT-5 family; a 128k model needs
  ~100000). Too high = hard API errors mid-ingestion; too low = merely more excerpts.
- Current models: chat/judge-fallback `gpt-5.4-mini`, strong parse+extraction
  `gpt-5.4`, embeddings `text-embedding-3-large` (multilingual — much of the corpus
  is French).

## Bench rules (the expensive part — treat with care)

- Design frozen in `studies/NOEMA_EVAL_BENCH.md`; datasets documented in
  `studies/BENCH_DATASETS.md` (QASPER + CRAG/FinanceBench/Basel-FAQ via the
  `noema-humanqa-v1` loader — human gold, pre-approved, no LLM drafting).
- **Never launch builds or runs yourself — the user launches and pays.** Respect the
  cost gate (estimate) before any build; builds are fingerprinted
  (corpus|cap|extractor|embed|`_EP_VERSION`) and build_skip reuses them. Anything
  that changes what a build produces (extraction prompts, episode windows) MUST bump
  `_EP_VERSION`; anything that changes query behavior (recipes, rerankers, judge
  rubric) MUST land in run provenance. Runs made under different settings never share
  a results table.
- Judging is decoupled and parallel (`JUDGE_CONCURRENCY`); `JUDGE_RPM` pacing is
  opt-in for free tiers only. Reports (schema v3) carry bootstrap CIs, paired McNemar
  on fusion, and priced run cost — keep new metrics additive and recomputable from
  stored records.

## Working style

- **CODE STYLE (SUPER IMPORTANT):** highly readable, self-explanatory code — clear
  names, small functions, obvious structure. Comment only where intent is genuinely
  non-obvious (constraints, measured decisions), never narrating the next line.
- Staged increments, smallest working slice first. Keep modules small and
  single-purpose. When a design choice isn't specified, surface options and
  trade-offs instead of silently picking one.
- Tests are plain-python scripts under `tests/` (`.venv/bin/python tests/test_*.py`),
  no-network wherever possible; run the relevant suites after touching their area.
- **Git:** never commit `backend/.env` or any key; `.claude/` stays gitignored (only
  this file is tracked); no AI/Co-Authored-By attribution trailers on commits or PRs.
  Knowledge stores (`.chroma`, graph saves, bench workdirs) are committed only as
  deliberate "refresh" commits — never fold store churn into feature commits.
- Free API tiers may only ever receive public benchmark corpora — never internal
  documents.
- Windows/prod portability matters (`RUN_ON_WINDOWS.md`): bundled FalkorDB is
  Unix-only (use `falkor_server`), the gateway may rate-limit harder
  (`GRAPH_MAX_COROUTINES`), and datasets are carried as files (no HF access).

## Where to look before working

| Topic | Read |
|---|---|
| Architecture tour, config, pipeline | `docs/01–11` |
| Bench design (frozen) + datasets | `studies/NOEMA_EVAL_BENCH.md`, `studies/BENCH_DATASETS.md` |
| Evolution contract (Phase 2) | `studies/NOEMA_EVOLUTION_CONTRACT.md` |
| Parsing / memory / SOTA decisions | `studies/NOEMA_PARSING_SOTA.md`, `studies/NOEMA_MEMORY_SOTA.md`, `studies/NOEMA_PLAN_LOG.md` |
| Deploying on the company machine | `RUN_ON_WINDOWS.md` |

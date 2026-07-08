# Backend tour — module by module

A guided walk through `backend/app/` so you know where everything lives, what it does,
and how the pieces connect. Each section gives the purpose, the key files, the main
types/functions, and the seams to the rest of the system. Deep dives live next to the
code — this page links to them instead of duplicating them.

The app is a FastAPI service (`uvicorn app.main:app` from `backend/`). One process hosts
everything: HTTP routers, the vector store (embedded Chroma), and the graph store
(a bundled FalkorDB server auto-started on demand).

## The big picture

```
routers/                                  (thin HTTP layer — one file per surface)
  │
  ├─ chat ───────────► pipeline.py ──┬──► retrieval/   (hybrid contextual vector base)
  │                                  └──► graph/       (Graphiti temporal knowledge graph)
  ├─ documents ──────► parsing/
  ├─ graphmem ───────► graph/ + parsing/ + retrieval/ (ingests into BOTH stores) + saves.py
  ├─ memory ─────────► memory_store.py + memory_judge.py
  ├─ conversations ──► conversation_store.py
  ├─ beliefs ────────► beliefs.py (+ pipeline.contextualize_note)
  └─ textgraph ──────► textgraph/   (DORMANT — kept, not wired to the current UI)

ingestion chain:  parsing/ ──► chunking/ ──► retrieval/ (contextualize → embed → store)
                      └─────────────────────► graph/    (one episode per page)

every model call, from every layer ──► llm_client.py ◄── config.py ◄── backend/.env
(the graph layer builds Graphiti's own clients in graph/providers.py, from the same config)
```

---

## 1. `main.py`, `config.py`, `llm_client.py` — app factory and the provider abstraction

This trio is the foundation. The single most important architectural rule of the
project lives here:

> **Only `llm_client.py` imports the OpenAI SDK.** No other file constructs a client,
> hardcodes a model name, or reads provider env vars. Switching providers is a `.env`
> change, never a code change.

| File | One-liner |
| --- | --- |
| `main.py` | FastAPI app factory: CORS for the Vite dev server (`localhost:5173`) + one `include_router` per surface. New surfaces slot in as new routers. |
| `config.py` | The ONLY place env vars are read. Loads `backend/.env`, validates, exposes a frozen `Settings` dataclass as the module-level `settings`. Fails fast at import on bad config (`ConfigError`). |
| `llm_client.py` | The provider-swap layer. Everything the app needs from a model goes through four functions: `chat()`, `embed()`, `transcribe_image()`, `list_models()`. |

### The two providers

`LLM_PROVIDER` in `.env` selects the backend at runtime:

- **`openai`** — dev (personal Mac, standard `api.openai.com`). Defaults:
  `gpt-5.4-mini` (chat), `text-embedding-3-large` (embeddings), `gpt-5.4` (vision parsing + graph extraction).
- **`llmaas`** — prod (the company's Azure-hosted, **OpenAI-compatible** gateway at a
  custom `LLMAAS_BASE_URL`). Same SDK, different `base_url`; model names are whatever
  the endpoint expects (`LLMAAS_CHAT_MODEL`, …). The API key may be blank for keyless
  gateways — `llm_client` passes a placeholder string the server ignores (the SDK
  refuses an empty key).

There is deliberately no `AzureOpenAI` SDK branch: because the prod endpoint is
OpenAI-compatible, one SDK with a different `base_url` covers both.

### `llm_client.py` surface

```python
from app import llm_client

res = llm_client.chat(messages)                      # ChatResult(text, usage, model)
for ev in llm_client.chat(messages, stream=True):    # StreamEvent(type="delta"|"usage")
    ...
vecs = llm_client.embed(["some text"])               # list[list[float]], order preserved
res = llm_client.transcribe_image(b64_png, prompt)   # vision call (PDF page → Markdown)
ids = llm_client.list_models()                       # what /v1/models exposes
```

Types: `Message` (role/content dict), `Usage` (includes `cached_tokens` — the
prompt-prefix-cache hits that make Contextual Retrieval cheap), `ChatResult`,
`StreamEvent`.

Two robustness details worth knowing:

- `_common_kwargs()` only includes `max_tokens` when actually set — newer models
  (gpt-5, o-series) reject the legacy param even as null.
- `_create()` retries once without `temperature` on a temperature-related 400 —
  reasoning models only accept the default. Generic on purpose: no per-model table.

`Settings` also carries non-LLM knobs read once here and consumed elsewhere: `parser`
(+ Document Intelligence credentials), `vector_dir`, `beliefs_dir`, the reranker seam
(`rerank_model` / `rerank_base_url` / `rerank_api_key`), `chat_temperature`,
`max_history_turns`.

---

## 2. Small stores and shared shapes

| File | One-liner |
| --- | --- |
| `schemas.py` | Pydantic request bodies shared across routers (responses stay plain dicts): `ChatMessage`, `ChatRequest` (with `model`, `domain`, `memory`, `use_memory`), `MemoryRequest`, `ConversationSave`, `ConversationRename`. |
| `conversation_store.py` | Durable conversations in SQLite (`conversations.db` next to the module, gitignored/disposable). One row per conversation; messages + persona + attached documents in a single JSON `data` column. `list_summaries() / get() / upsert() / rename() / delete() / clear()`. |
| `memory_store.py` | Persistent **user** facts (from `/remember` and the memory judge) as a hand-editable Markdown file (`memory.md`, one fact per `- ` line). Migrates a legacy `memory.json` once. `load_memories() / add_memory() / remove_memory() / clear_memories()`. |
| `memory_judge.py` | The automatic counterpart to `/remember`: `extract_facts(messages, known)` runs one cheap chat call that extracts durable, user-confirmed facts ("only trust the USER" — never the assistant's guesses) and parses the JSON reply leniently. |
| `beliefs.py` | The user's own notes/opinions per memory context — NOT part of the corpus, never embedded. One small Markdown file per `(user, context)` under `.beliefs/`; `context_key(domain, memory)` = the selected save, else the live domain (exactly what the chat answers from). `read_beliefs() / write_beliefs() / append_belief()`, capped at 8 000 chars. |
| `saves.py` | Named checkpoints ("saves") of a domain's **whole memory** — and the owner of the operations, not just the naming. |

### `saves.py` in one breath

A save captures **both stores under one key** so they stay in lockstep:

- the Graphiti graph — a FalkorDB graph copied via `GRAPH.COPY` (`graph/server.falkor_ops`),
- the RAG vector base — a Chroma collection copied via `VectorStore.copy_into`.

Naming: `save_key("default", "v1")` → `__save__default__v1`. The subtle part is
`base_group_id()`: a save graph is a *raw copy*, so its nodes keep the base domain's
`group_id`. When `GraphMemory` opens a save, it connects to the save's graph but
filters by the base `group_id` — they differ only for saves.

Operations (all sync; async callers wrap in `asyncio.to_thread`): `list_saves`,
`create_save` (refuses an empty graph), `restore_save` (overwrites the live domain,
both stores), `delete_save`. Graph/retrieval imports are lazy on purpose —
`graph/store.py` imports `base_group_id` from here at module load, so a top-level
import back would be circular.

---

## 3. `parsing/` — PDF → Markdown

**Deep dive: [`parsing/PARSING.md`](../backend/app/parsing/PARSING.md).**

The only code in the app that knows how to read a PDF. Everything downstream consumes
its Markdown.

| File | One-liner |
| --- | --- |
| `base.py` | The shared contract: `ParsedDoc` (filename, per-page Markdown, token counts, per-page `routes`) and `ParseError`. |
| `dispatch.py` | `parse_document(data, filename)` — picks the backend from `PARSER` in `.env`, mirrors the LLM provider seam. Callers never care which ran. |
| `vision.py` | The default backend. Per-page tiered routing: a page that is confidently clean prose **and** figure-free uses its free text layer (lightly promoted to Markdown); anything else (garbled text, math signals, a raster image ≥3% of the page, ≥15 vector paths) is rendered with pypdfium2 and transcribed by a vision LLM into Markdown + LaTeX, with a detailed figure-extraction prompt. Also exports `render_pages()`. |
| `docintel.py` | Azure Document Intelligence (`prebuilt-layout`, formulas → LaTeX, Markdown output). Deterministic, in-tenant — the prod backbone track. |

> **Status note on `docintel`:** it is wired and import-verified against the GA SDK
> (1.0.x) but has **not yet been run against a live Azure DI resource** (none exists
> on the dev machine). Validate it on the company's Azure DI before relying on it.

Connections: `routers/documents.py` (chat PDF attach), `routers/graphmem.py` (graph
ingestion), and `retrieval/ingest.py` all call `parsing.parse_document`. The vision
path goes through `llm_client.transcribe_image`, so it inherits the provider swap.

---

## 4. `chunking/` — Markdown → provenance-tagged chunks

**Deep dive: [`chunking/CHUNKING.md`](../backend/app/chunking/CHUNKING.md).**

| File | One-liner |
| --- | --- |
| `base.py` | The `Chunk` dataclass: text plus everything needed to cite it — `doc_id`, `pages`, `header_path` (→ `section`), token counts, `domain_id`. |
| `markdown_chunker.py` | Structure-aware recursive chunker: cut on headings, then paragraphs/sentences, size-bound to ~512 tokens with a small overlap. Atomic blocks (fenced code, `$$…$$` math, HTML tables) are never split. `chunk_parsed_doc()` keeps page provenance from the per-page Markdown; `chunk_markdown()` handles raw Markdown. |
| `tokens.py` | Default token counter: exact tiktoken (`o200k_base`) when its vocab loads, else a ~4-chars-per-token heuristic. Pluggable so the locked-down prod box (which may not fetch tiktoken's vocab) still works. |

Semantic/embedding chunking is deliberately not used — the gains come later, from
contextualization.

---

## 5. `retrieval/` — the contextual vector base

**Deep dives: [`retrieval/RETRIEVAL.md`](../backend/app/retrieval/RETRIEVAL.md) and
[`retrieval/CONTEXTUAL.md`](../backend/app/retrieval/CONTEXTUAL.md).**

```
ingest:  PDF/Markdown ─► parse ─► chunk ─► contextualize ─► embed ─► store (Chroma)
query:   question ─► [dense ‖ BM25] ─► fuse (RRF) ─► rerank? ─► top-k ─► cited answer
```

| File | One-liner |
| --- | --- |
| `base.py` | The stable retrieval contract: `ScoredChunk` (original `text` for citing vs `context` blurb for indexing; `citation`, `embed_text`, per-stage `scores`), `RetrievalTrace` (every stage of a query), `Answer`. |
| `store.py` | `VectorStore` — embedded, on-disk Chroma, one collection per `domain_id`, cosine space. `add()` (upsert — incremental by design), `query()`, `all_records()`, plus the snapshot seam `copy_into()` / `drop()` used by `saves.py`. |
| `bm25.py` | Pure-Python Okapi BM25 over the chunks' contextual text — the lexical half of hybrid search. No model, no GPU, no dependency. |
| `search.py` | Hybrid search: dense + BM25, fused with **`rrf()` — the ONE shared Reciprocal Rank Fusion implementation** (the expert pipeline fuses graph + vector with the same function). `search_trace()` returns every stage; `search()` returns just the final list. |
| `contextual.py` | Anthropic Contextual Retrieval: one LLM call per chunk writes a blurb situating it in its document; the blurb is prepended before embedding/BM25. The document sits at the *start* of the prompt so repeated calls hit the provider's prompt-prefix cache. `ContextualChunk`, `contextualize_chunks()`. |
| `ingest.py` | The orchestrator that chains it all: `ingest_pdf()` / `ingest_parsed_doc()` / `ingest_markdown()` → parse → chunk → contextualize → embed → store. Returns chunk/token accounting. |
| `answer.py` | Grounded answering: `answer_from(query, chunks)` builds a numbered-source prompt (`[S1]`, `[S2]`…), constrains the model to those sources, answers in the question's language. |
| `rerank.py` | Optional reranker seam, three no-GPU modes: `off` (default pass-through), `llm` (RankGPT-style single call through the normal chat endpoint), `endpoint` (hosted cross-encoder, Cohere/Jina request shape, enabled by `RERANK_MODEL` + `RERANK_BASE_URL`). |

Connections: the expert `pipeline.py` calls `search_trace()` and reuses `rrf()`;
`routers/graphmem.py` calls `ingest_parsed_doc` / `ingest_markdown` so every graph
ingestion also lands in the vector base; `saves.py` snapshots collections.

---

## 6. `graph/` — the Graphiti temporal knowledge graph

**Deep dive: [`graph/GRAPH.md`](../backend/app/graph/GRAPH.md).**

The second memory over the same documents: entities + temporal facts, LLM-extracted,
persisted in FalkorDB. One graph per domain.

| File | One-liner |
| --- | --- |
| `config.py` | `GraphConfig` / `graph_config` — backend selection via `GRAPH_BACKEND`: `falkor_local` (default: auto-runs the FalkorDB server bundled inside falkordblite, port 6399), `falkor_embedded` (flaky under concurrent writes), `falkor_server` (external, e.g. Docker on Windows), `neo4j`. LLM credentials deliberately NOT duplicated here — they come from `app.config`. |
| `server.py` | Runs the bundled FalkorDB binary as one shared local process (`ensure_local_server`, idempotent, stopped at exit) **and** the raw graph-admin helpers: `falkor_ops(fn)` (short-lived sync client), `list_graphs()`, `copy_graph(src, dest)` (`GRAPH.COPY`, overwrites), `drop_graph(name)`. These back saves and Dream checkpoints. |
| `base.py` | Flat, JSON-serializable shapes: `GraphFact` (a retrieved edge with temporal validity + `episodes` provenance), `GraphNode`, `GraphEdge`, `GraphSnapshot`. |
| `store.py` | `GraphMemory` — the whole layer behind a small async surface: `build()`, `add_episode()` (extract → resolve → relate → invalidate; incremental, never rebuilds), `search()` (skips Dream-archived facts), `snapshot()` (ALL nodes/edges incl. invalidated — temporal history stays visible), `episode_names()` (episode uuid → `"<file> · p<N>"`, the provenance the pipeline cites), `reset()`. Gotcha encoded here: the FalkorDriver's `database` must equal the `domain_id`, while data is filtered by `base_group_id(domain_id)`. |
| `manager.py` | `graph_manager` — the shared cache of `GraphMemory` instances, one per `(domain, extract-model)`. Both the graphmem router (writes) and the pipeline (reads) go through it so there is exactly ONE FalkorDriver per domain bound to the app's event loop. `lock(domain)` serializes writes; reads don't take it. |
| `providers.py` | Builds Graphiti's own LLM + embedder clients from `app.config.settings` — the single sanctioned place the graph layer touches model config. Extraction defaults to the strong `parse_model` (a weak extractor yields a sparse graph); `llmaas` gets `OpenAIGenericClient` (custom base_url, looser structured output). |
| `schema.py` | Domain-adaptive extraction: `induce_schema(sample, domain=…)` — one LLM pass over a corpus sample derives the domain's entity/edge types; `schema_instructions()` turns that into an extraction instruction; persisted per domain (`save_schema`/`load_schema`) and auto-applied by `GraphMemory`. |
| `evolution.py` | **Dream** — one self-maintenance cycle: analyze → plan → passes (`dedupe` duplicate entities via fuzzy match + LLM confirmation, `forget` = archive long-superseded facts + prune orphans, `consolidate` = community summaries, off by default). Every pass runs against a `GRAPH.COPY` checkpoint, is sanity-checked after (`_check`: episodes intact, no current fact lost, retrieval still answers), and rolls back on failure. Episodes are never touched; facts are archived, not deleted. `dream(domain)` is an async generator of progress events. |
| `viz.py` | `render_html(snapshot)` — self-contained interactive vis-network HTML (current facts solid, invalidated dashed). Used by the lab/tests; the product UI renders its own 3D view. |

Connections: `pipeline.graph_chunks()` adapts `GraphFact`s into `ScoredChunk`s so the
graph fuses and cites like any other retriever; `routers/graphmem.py` streams per-page
extraction; `saves.py` copies whole graphs.

---

## 7. `textgraph/` — DORMANT

An InfraNodus-style word co-occurrence network: instant, no LLM, computed on ingest,
one JSON per domain. It was built as a first graph lens, then the `?view=graph` page
was repointed to the real Graphiti memory. **Kept as a possible future "instant" lens;
not used by the current UI.** Its router still mounts at `/textgraph`.

| File | One-liner |
| --- | --- |
| `cooccurrence.py` | Tokenize (unicode letters, stopwords out) and fold tokens into node counts + sliding-window (4-gram) edge weights, 1/distance. |
| `store.py` | `TextGraphMemory` — persistent counts, incremental `ingest()`, `snapshot(limit)` returns the top-N sub-network for a browser to lay out. |
| `stopwords.py` | The stopword list. |

---

## 8. `routers/` — the thin HTTP layer

Each file is one product surface; logic lives in the modules above. See the
[API reference](08-api-reference.md) for endpoints and payloads.

| Router | One-liner |
| --- | --- |
| `system.py` | `/health` liveness + `/models` (chat-capable model catalogue with an exclusion heuristic, plus the configured default). |
| `chat.py` | `POST /chat` — SSE stream; plain chat (`use_memory=false`) or the expert pipeline (status/sources/delta/usage events); trims history to `max_history_turns`; `POST /title` auto-names a conversation. |
| `memory.py` | CRUD on the user-fact memory + `POST /memory/auto` (the LLM memory judge). |
| `documents.py` | `POST /upload` — PDF → parsed Markdown for chat attachment (25 MB cap). |
| `conversations.py` | List/load/upsert (PUT is an upsert — the frontend generates ids)/rename/delete/clear conversations. |
| `graphmem.py` | The real graph memory surface: snapshot, text ingest, **streamed** PDF upload (NDJSON, one event per extracted page, then RAG indexing of the same parse), Dream (streamed), reset, and the save/restore/delete-save checkpoints. Ingestion here writes BOTH stores. |
| `beliefs.py` | Read/write the user's notes per memory context + `/beliefs/add` (the `/note` command; resolves references via `pipeline.contextualize_note` without altering the claim). |
| `textgraph.py` | The dormant co-occurrence surface (ingest/snapshot/reset). |

---

## 9. `pipeline.py` — the expert brain

The answer engine behind `POST /chat` when memory is on. In one line:

```
route (rewrite to standalone query + "needs retrieval?")
  → retrieve (vector search_trace ‖ graph facts, RRF-fused via retrieval.rrf)
  → grade sufficiency (CRAG-style, before answering)
  → grounded answer (sources + the user's beliefs as separate blocks)
  → grade faithfulness (Self-RAG-style, after)
  → retry (max 2) or answer, streaming status/delta/sources/usage events
```

Key pieces: `graph_chunks()` (the `GraphFact` → `ScoredChunk` adapter that parses
`"<file> · p<N>"` episode names back into doc + page provenance), `retrieve()` (the
fusion), `answer_stream()` (the agentic loop, async generator of event dicts),
`contextualize_note()` (cleans a `/note` against recent chat without changing the
claim). All judgements are single cheap buffered calls (`_judge_sync`) that fail open.

**The full walkthrough is in the [expert pipeline deep dive](05-expert-pipeline.md).**

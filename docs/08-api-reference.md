# HTTP API reference

This page documents every endpoint the FastAPI backend exposes, grouped by router
(`backend/app/routers/`). For each: method and path, purpose, request shape, response
shape, and a curl example. Two endpoints stream: `POST /chat` streams **Server-Sent
Events**, and `POST /graphmem/upload` / `POST /graphmem/dream` stream **NDJSON** (one JSON
object per line); their full event protocols are given below. The base URL is
`http://localhost:8000` in dev (the frontend reads it from `VITE_API_BASE` — see
[Configuration](03-configuration.md)). Request bodies come from `app/schemas.py` unless a
router defines its own Pydantic model; responses are plain dicts.

## System (`routers/system.py`)

### `GET /health`

Liveness probe.

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

### `GET /models`

Chat-capable models at the configured endpoint, plus the configured default. Non-chat
model families (embeddings, whisper, tts, image, …) are filtered out by name fragment —
an exclusion heuristic, so an unknown enterprise chat model is never hidden. If the
endpoint cannot list models, returns an empty list (still with the default) so the UI
always has something to select.

```bash
curl http://localhost:8000/models
# {"models": ["gpt-4.1-mini", "gpt-4o", ...], "default": "gpt-4.1-mini"}
```

## Chat (`routers/chat.py`)

### `POST /chat` — streams SSE

The conversation itself. Request body (`ChatRequest`):

| Field | Type | Default | Meaning |
|---|---|---|---|
| `messages` | `[{role, content}]` | required | The conversation so far. History is trimmed to `MAX_HISTORY_TURNS` recent turns; system messages always stay. |
| `model` | `string \| null` | `null` | Override the configured chat model. |
| `domain` | `string \| null` | `"default"` | Which knowledge base (memory domain) to ground answers in. |
| `memory` | `string \| null` | `null` | A saved snapshot name to answer from (`null` = live memory). |
| `use_memory` | `bool` | `true` | `true` = run the expert pipeline (route → retrieve → grade → answer → verify); `false` = plain chat. |

The response is `text/event-stream`. Every frame is `data: <json>\n\n` where the JSON
carries a `type` field; the stream always ends with `data: [DONE]\n\n`. A provider or
pipeline error mid-stream becomes an `error` event, not a dead connection.

**Plain mode** (`use_memory: false`) emits only:

```
data: {"type": "delta", "text": "Hello! How can"}
data: {"type": "delta", "text": " I help?"}
data: {"type": "usage", "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20, "cached_tokens": 0}}
data: [DONE]
```

**Expert mode** (`use_memory: true`, the default) additionally streams `status` events
(the live runtime trace) and a `sources` event. Event types, in the order they can occur
(see `pipeline.answer_stream`):

| Event `type` | Payload | Meaning |
|---|---|---|
| `status` | `stage`, `detail` | One step of the runtime trace (stages below). |
| `delta` | `text` | A piece of the answer text. |
| `sources` | `sources: [...]` | What the answer is grounded on (shape below). Emitted once, after the deltas. |
| `usage` | `usage: {prompt_tokens, completion_tokens, total_tokens, cached_tokens}` or `null` | Token counts of the answering call. Always the last event before `[DONE]`. |
| `error` | `message` | A pipeline/provider error, surfaced to the UI. |

`status` stages:

| `stage` | When |
|---|---|
| `routing` | Reading the question in context (rewrite to a standalone query + decide if retrieval is needed). |
| `contextualized` | The question was rewritten; `detail` shows the standalone query. |
| `beliefs` | The user has notes for this memory context; they will be weighed alongside the answer. |
| `direct` | No retrieval needed — answering directly (the stream then goes straight to `delta`/`usage`, with no `sources` event). |
| `route` | Retrieval is needed. |
| `retrieving` | Searching the vector base + graph (attempt 1), or retrieving more and re-fusing (retry). |
| `retrieved` | Result counts, e.g. `"8 sources · 8 vector · 6 graph"`. |
| `grading` | CRAG check: do the sources cover the question? |
| `insufficient` | They do not — retrieving more (only when a retry remains). |
| `answering` | Composing the grounded answer. |
| `verifying` | Self-RAG check: is the answer supported by the sources? |
| `grounded` / `ungrounded` | Verification verdict (`ungrounded` = answering with a caveat after the last attempt). |
| `redoing` | Retrying: nothing found, or the answer was not grounded (max 2 attempts). |
| `empty` | No matching sources at all — a fixed "couldn't find anything" answer is streamed. |

Each entry in `sources`:

```json
{
  "n": 1,
  "citation": "paper.pdf, p.3",
  "doc_id": "paper.pdf",
  "pages": [3],
  "section": "Methods",
  "text": "The exponents satisfy a duality relation...",
  "origin": "vector",
  "score": 0.03252
}
```

`origin` is `"graph"` for chunks that came from the Graphiti graph (their `chunk_id`
starts with `graph:`), `"vector"` otherwise.

Example (note `-N` to disable curl buffering):

```bash
curl -N http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{
        "messages": [{"role": "user", "content": "What shifted the crystal frequency?"}],
        "domain": "default",
        "use_memory": true
      }'
```

Example frames:

```
data: {"type": "status", "stage": "routing", "detail": "Reading the question in context…"}
data: {"type": "status", "stage": "route", "detail": "This needs the knowledge base"}
data: {"type": "status", "stage": "retrieving", "detail": "Searching the vector base + graph…"}
data: {"type": "status", "stage": "retrieved", "detail": "8 sources · 8 vector · 6 graph"}
data: {"type": "status", "stage": "grading", "detail": "Checking the sources cover the question…"}
data: {"type": "status", "stage": "answering", "detail": "Composing a grounded answer…"}
data: {"type": "status", "stage": "verifying", "detail": "Checking the answer is grounded in the sources…"}
data: {"type": "status", "stage": "grounded", "detail": "Grounded in the sources ✓"}
data: {"type": "delta", "text": "The resonance cascade shifted the cry"}
data: {"type": "delta", "text": "stal frequency to 7.83 Hz [S1]."}
data: {"type": "sources", "sources": [{"n": 1, "citation": "resonance_of_sector_7.pdf, p.2", ...}]}
data: {"type": "usage", "usage": {"prompt_tokens": 2110, "completion_tokens": 64, "total_tokens": 2174, "cached_tokens": 0}}
data: [DONE]
```

### `POST /title`

Name a conversation from its first exchange (cheap buffered call, max 16 tokens). Body is
a `ChatRequest`; only `messages` is used (each message clipped to 300 chars).

```bash
curl http://localhost:8000/title \
  -H 'Content-Type: application/json' \
  -d '{"messages": [{"role": "user", "content": "Explain Hölder inequalities"},
                    {"role": "assistant", "content": "They bound the sum of products..."}]}'
# {"title": "Hölder Inequality Explained"}
```

## Memory — user facts (`routers/memory.py`, prefix `/memory`)

Persistent facts about the *user* (saved via the chat's `/remember` command or the LLM
judge). Distinct from the document/graph memory. All endpoints return the updated list.

| Method + path | Body | Purpose |
|---|---|---|
| `GET /memory` | — | Return the persisted facts: `{"memories": ["..."]}`. |
| `POST /memory` | `{"fact": "..."}` | Persist one fact. |
| `POST /memory/remove` | `{"fact": "..."}` | Remove one saved fact. |
| `DELETE /memory` | — | Clear all saved facts. |
| `POST /memory/auto` | `ChatRequest` (only `messages` used) | LLM-judged: extract durable facts from a recent exchange. Returns `{"added": [...], "memories": [...]}` so the UI can both confirm and refresh. |

```bash
curl -X POST http://localhost:8000/memory \
  -H 'Content-Type: application/json' \
  -d '{"fact": "The user prefers answers in French."}'
# {"memories": ["The user prefers answers in French."]}
```

## Documents (`routers/documents.py`)

### `POST /upload`

Parse a PDF (vision LLM or Azure Document Intelligence, per `PARSER` in `.env`) and return
its Markdown. Used by the chat page for prompt-stuffed attachments. Multipart form with a
`file` field. Rejects non-PDFs (`400`) and files over 25 MB (`413`); parse failures come
back as `400` with a clear message.

```bash
curl -X POST http://localhost:8000/upload -F 'file=@paper.pdf'
# {"filename": "paper.pdf", "pages": 12, "chars": 48210, "text": "# Title\n\n..."}
```

## Conversations (`routers/conversations.py`, prefix `/conversations`)

Durable conversation store. The **frontend generates the conversation id**, so `PUT` is an
upsert — it creates the conversation on first save and updates it thereafter.

| Method + path | Body | Purpose |
|---|---|---|
| `GET /conversations` | — | Lightweight summaries for the sidebar (no message bodies): `{"conversations": [...]}`. |
| `DELETE /conversations` | — | Delete all conversations (`204`). |
| `GET /conversations/{id}` | — | The full conversation; `404` if unknown. |
| `PUT /conversations/{id}` | `{"title": "", "character": "", "messages": [], "documents": []}` | Upsert (all fields optional, defaults shown). |
| `PATCH /conversations/{id}` | `{"title": "..."}` | Rename; `404` if unknown. Returns `{"id", "title"}`. |
| `DELETE /conversations/{id}` | — | Delete one (`204`); `404` if unknown. |

```bash
curl -X PUT http://localhost:8000/conversations/c42 \
  -H 'Content-Type: application/json' \
  -d '{"title": "Hölder chat", "messages": [{"role": "user", "content": "hi"}]}'
```

## Text graph (`routers/textgraph.py`, prefix `/textgraph`) — dormant

An InfraNodus-style **word co-occurrence** graph (instant, no LLM). The router is kept and
functional, but the current UI no longer uses it — the `?view=graph` page was repointed to
the Graphiti memory (`/graphmem`). Kept as a possible future "instant" lens.

| Method + path | Body / params | Purpose |
|---|---|---|
| `GET /textgraph` | `?limit=160` | Snapshot of the salient word network. |
| `POST /textgraph/ingest` | `{"text": "...", "source": "..."}`, `?limit=160` | Fold pasted text into the graph; `400` if empty. Returns the snapshot. |
| `POST /textgraph/upload` | multipart `file` (+ optional `model` form field), `?limit=160` | Parse a PDF and fold it in. Same PDF checks as `/upload` (25 MB, `400`/`413`). |
| `POST /textgraph/reset` | — | Clear the graph; returns the empty snapshot. |

## Graph memory (`routers/graphmem.py`, prefix `/graphmem`)

The **real** memory: Graphiti — LLM-extracted entities, relationships and temporal facts,
persisted in FalkorDB. Ingestion also folds the same content into the RAG vector base
(chunk → contextualize → embed → store) so one corpus is queryable both ways. The optional
`model` on ingest endpoints picks the **extraction** model (the one that builds the graph).

All non-streaming endpoints return the same graph payload:

```json
{
  "nodes": [{"id": "<uuid>", "name": "Marie Curie", "labels": ["Entity"], "summary": "..."}],
  "links": [{
    "source": "<uuid>", "target": "<uuid>",
    "name": "DISCOVERED", "fact": "Marie Curie discovered radium",
    "is_current": true, "valid_at": "2026-03-01T00:00:00Z", "invalid_at": null,
    "created_at": "2026-06-30T09:12:44Z"
  }],
  "stats": {"node_count": 12, "edge_count": 18, "current_edges": 16, "invalidated_edges": 2}
}
```

### `GET /graphmem?domain=default`

Snapshot of a domain's graph.

```bash
curl 'http://localhost:8000/graphmem?domain=default'
```

### `POST /graphmem/ingest`

Fold pasted text into the graph as one episode, then (best-effort) into the RAG base.
Body: `{"text": "...", "source": "...", "model": null, "domain": null}` (`source` defaults
to `"pasted text"`, `domain` to `"default"`). `400` if the text is empty. Returns the
graph payload.

```bash
curl -X POST http://localhost:8000/graphmem/ingest \
  -H 'Content-Type: application/json' \
  -d '{"text": "Marie Curie discovered radium in Paris.", "source": "note"}'
```

### `POST /graphmem/upload` — streams NDJSON

Parse a PDF, then extract page by page into the graph, streaming a fresh snapshot after
each page so the 3D page can draw the graph as it grows; finally index the parsed document
into the RAG vector base. Multipart form: `file` (PDF, max 25 MB), optional `model` and
`domain` fields. The response is `application/x-ndjson` — one JSON object per line:

| `phase` | Extra fields | Meaning |
|---|---|---|
| `parsing` | `filename` | Parse started (vision LLM). |
| `parsed` | `filename`, `pages` | Parse finished; `pages` = non-empty pages to extract. |
| `page` | `page`, `total`, + full graph payload (`nodes`, `links`, `stats`) | One page extracted; snapshot after it. |
| `error` | `detail` (+ `page` when a single page failed) | A parse error ends the stream; a per-page extraction error is reported and the stream continues. |
| `rag_indexing` | `filename` | Started indexing into the RAG vector base (reuses the parse — no second vision pass). |
| `rag_done` | `filename`, `chunks` | RAG indexing finished. |
| `rag_error` | `filename`, `detail` | RAG indexing failed — reported, never loses the graph work. |
| `done` | — | Stream complete. |

```bash
curl -N -X POST http://localhost:8000/graphmem/upload \
  -F 'file=@paper.pdf' -F 'domain=default'
```

Example lines:

```
{"phase": "parsing", "filename": "paper.pdf"}
{"phase": "parsed", "filename": "paper.pdf", "pages": 4}
{"phase": "page", "page": 1, "total": 4, "nodes": [...], "links": [...], "stats": {"node_count": 6, ...}}
{"phase": "page", "page": 2, "total": 4, "nodes": [...], "links": [...], "stats": {"node_count": 11, ...}}
{"phase": "rag_indexing", "filename": "paper.pdf"}
{"phase": "rag_done", "filename": "paper.pdf", "chunks": 23}
{"phase": "done"}
```

### `POST /graphmem/dream` — streams NDJSON

One gated self-maintenance cycle (dedupe → forget → consolidate), streamed so the page can
narrate each pass and redraw the graph as it changes. Body:
`{"domain": null, "model": null}`. Each pass runs against a `GRAPH.COPY` checkpoint and is
sanity-checked after — rolled back if it lost knowledge. Requires a FalkorDB server
backend (`falkor_local` or `falkor_server`). Tunables: `DREAM_GRACE_DAYS`,
`DREAM_COMMUNITIES`, `DREAM_CONSOLIDATE_TIMEOUT_S` — see
[Configuration](03-configuration.md). Events (`app/graph/evolution.py, dream()`):

| `phase` | Extra fields | Meaning |
|---|---|---|
| `error` | `detail` | Wrong backend, unreadable graph, or inconsistent read — Dream refuses to run. |
| `analyze` | `nodes`, `edges` | Current graph size. |
| `plan` | `passes: [{key, reason}]` | Which passes will run and why (e.g. `{"key": "dedupe", "reason": "1 exact + 2 likely duplicate entities"}`). |
| `pass_start` | `pass`, `reason` | A pass begins (after checkpointing). |
| `pass_done` | `pass`, `changes`, + full graph payload | Pass succeeded. `changes` per pass: dedupe → `{merged, details}`; forget → `{archived, pruned_orphans}`; consolidate → `{communities}`. |
| `pass_rolled_back` | `pass`, `why`, + full graph payload | The post-pass check failed (e.g. `"2 current facts lost"`) — restored from the checkpoint. |
| `done` | `summary` (+ `detail` when nothing ran) | Cycle complete. `summary` maps pass key → its `changes`. `detail` is e.g. `"The memory is empty."` or `"Nothing to improve."`. |

```bash
curl -N -X POST http://localhost:8000/graphmem/dream \
  -H 'Content-Type: application/json' -d '{"domain": "default"}'
```

Example lines:

```
{"phase": "analyze", "nodes": 42, "edges": 67}
{"phase": "plan", "passes": [{"key": "dedupe", "reason": "0 exact + 1 likely duplicate entities"}]}
{"phase": "pass_start", "pass": "dedupe", "reason": "0 exact + 1 likely duplicate entities"}
{"phase": "pass_done", "pass": "dedupe", "changes": {"merged": 1, "details": ["BNPP → BNP Paribas"]}, "nodes": [...], "links": [...], "stats": {...}}
{"phase": "done", "summary": {"dedupe": {"merged": 1, "details": ["BNPP → BNP Paribas"]}}}
```

### `POST /graphmem/reset?domain=default`

Clear a domain's graph. Returns the (empty) graph payload.

### Saves — full-memory checkpoints

A save captures **both** stores under one key (the FalkorDB graph via `GRAPH.COPY` and the
Chroma collection), so graph and RAG base stay in lockstep (`app/saves.py`). A saved
snapshot can then be answered from via `ChatRequest.memory`.

| Method + path | Body / params | Purpose |
|---|---|---|
| `GET /graphmem/saves` | `?domain=default` | List save names: `{"saves": ["v1", "before-dream"]}`. |
| `POST /graphmem/save` | `{"name": "v1", "domain": null}` | Checkpoint the domain. `400` if the name is blank or the graph is empty. Returns `{"saved": "v1", "chunks": 23}` (chunks captured from the vector base). |
| `POST /graphmem/restore` | `{"name": "v1", "domain": null}` | Overwrite the live domain with the save (both stores). `404` if the save doesn't exist. Returns the graph payload. |
| `POST /graphmem/delete-save` | `{"name": "v1", "domain": null}` | Delete a save. Returns `{"deleted": "v1"}`. |

```bash
curl -X POST http://localhost:8000/graphmem/save \
  -H 'Content-Type: application/json' -d '{"name": "v1"}'
```

## Beliefs (`routers/beliefs.py`, prefix `/beliefs`)

The user's own notes per memory context — **not** ingested into the graph or RAG; the
pipeline injects them into the answer prompt so the expert weighs them against the corpus
("the sources say X, your note says Y"). One small markdown file per (user, context);
context = the selected save name, else the live domain (`beliefs.context_key`).

| Method + path | Body / params | Purpose |
|---|---|---|
| `GET /beliefs` | `?domain=...&memory=...` | Read the notes: `{"context": "default", "text": "- ..."}`. |
| `POST /beliefs` | `{"text": "...", "domain": null, "memory": null}` | Overwrite the notes for a context (empty text clears them, max 8000 chars). Returns `{"context", "chars"}`. |
| `POST /beliefs/add` | `{"text": "...", "domain": null, "memory": null, "messages": [...]}` | Append one note (the chat's `/note` command). When `messages` (recent turns) are provided, pronouns/references are resolved against them first — the claim itself is never altered. Returns `{"context", "chars", "note"}` (the note as saved). |

```bash
curl -X POST http://localhost:8000/beliefs/add \
  -H 'Content-Type: application/json' \
  -d '{"text": "note that I think its estimate is too optimistic",
       "messages": [{"role": "assistant", "content": "The paper estimates a 40% gain..."}]}'
# {"context": "default", "chars": 58, "note": "I think the paper'\''s 40% gain estimate is too optimistic"}
```

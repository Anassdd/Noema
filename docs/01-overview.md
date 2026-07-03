# 01 — Overview & architecture

What Noema is, how its pieces fit, and the design rules that shaped it. Read this first;
every other doc zooms into one part of this picture.

## The concept

Noema is a **domain expert you build from documents**. Instead of asking a general-purpose
LLM to "remember" a corpus, Noema turns the corpus into an explicit, inspectable **memory**,
and the chat answers *from that memory* with citations. Three ideas run through everything:

1. **Memory is a first-class artifact** — you can see it (3D graph), version it (saves),
   annotate it (beliefs), and maintain it (Dream). It is not an opaque index.
2. **Provenance everywhere** — every chunk, fact, and edge traces back to its source
   document and page, so every answer can cite.
3. **One provider seam** — all LLM/embedding traffic goes through a single module, so the
   same code runs on a personal OpenAI key or a locked-down corporate endpoint.

## The two memories (and why both)

The same ingested pages feed two representations:

| | Contextual vector base (`retrieval/`) | Temporal knowledge graph (`graph/`) |
|---|---|---|
| Holds | LLM-situated chunks, embedded + BM25-indexed | entities, relationships, facts with time validity |
| Best at | "find me the passage" — most factual questions | relations, multi-hop, "what changed when" |
| Technique | Anthropic Contextual Retrieval (blurb → embed) | Graphiti (extract → resolve → invalidate) |
| Cost | one cheap LLM call per chunk at ingest | several LLM calls per page at ingest |

Research (see `studies/NOEMA_MEMORY_SOTA.md`) says the contextual hybrid base carries most
of the load and the graph is a corpus-dependent add-on — so Noema **fuses both at query
time** instead of betting on either: the graph is treated as *just another retriever* whose
results merge with the vector ranking via Reciprocal Rank Fusion. A wrong bet costs a few
rank positions, not the answer.

The two stay in lockstep because they ingest **the same parsed document** and share
provenance keys (the graph's episode names encode `file · page`, the same identity the
chunks carry).

## Flow 1 — Ingestion (Graph page)

```
PDF (drag-drop on /?view=graph)
 │
 ▼
parsing/          one Markdown string per page. Default: tiered vision parsing —
                  clean text pages use the free text layer, complex pages go to a
                  vision LLM. (Azure Document Intelligence available via PARSER.)
 │
 ├──────────────────────────────┐
 ▼                              ▼
graph/  (per page)              chunking/ → retrieval/
Graphiti extracts entities      structure-aware chunks (~512 tokens,
+ facts, resolves against       heading-aligned) → each gets an LLM
existing nodes, invalidates     "situating" blurb → embedded into
contradicted facts. The 3D      Chroma + indexed by BM25.
page redraws after each page.
```

Both writes are incremental — adding a document never rebuilds either store.

## Flow 2 — Expert answer (`pipeline.py`)

```
user question (+ recent turns)
 1. CONTEXTUALIZE+ROUTE   one LLM call: rewrite the message into a standalone query
    (resolves "him"/"that"/follow-ups, any language) AND decide if retrieval is
    needed at all (greetings/small talk skip it).
 2. RETRIEVE              vector search (dense+BM25+RRF) ⊕ graph search, then
    RRF-fuse the two rankings into one evidence set.
 3. GRADE (CRAG)          is the evidence sufficient for the question? If not,
    retry retrieval differently (bounded, max 2).
 4. ANSWER                grounded generation with inline [S1] citations; the user's
    BELIEFS for this memory context are injected as a separate block — if they
    contradict the sources, the answer presents both, attributed.
 5. VERIFY (Self-RAG)     is the draft faithful to the sources? If not, retry (bounded).
 → streamed to the UI as: status events (the visible trace) → answer tokens →
    sources → token usage.
```

## The kinds of memory (don't confuse them)

| Memory | Scope | Storage | Written by | Injected how |
|---|---|---|---|---|
| **Corpus** (vector + graph) | per domain / save | Chroma + FalkorDB | PDF ingestion | retrieved per-question |
| **Beliefs** | per memory context | Markdown file | ✎ panel or `/note` | verbatim block in every expert answer |
| **Personal memory** | global, all chats | `app/memory.md` | `/remember` + auto-judge | system prompt |
| **Conversation** | per chat | SQLite | automatic | it *is* the chat history |
| **Chat PDFs** | per conversation | in the conversation | attach in chat | stuffed into the system prompt if the total fits the token budget |

"Memory context" = the selected save, else the live domain — beliefs are keyed by it, and
the expert answers from it.

## Saves, and Dream in one paragraph each

**Saves** are named checkpoints of the *whole* memory: the FalkorDB graph is copied via
`GRAPH.COPY` and the Chroma collection is copied under the same key, so graph and vector
base always restore together. `app/saves.py` owns this.

**Dream** is user-triggered self-maintenance of the graph: analyze → plan → for each pass
(merge duplicate entities; archive long-superseded facts; prune orphan debris) checkpoint →
run → sanity-check → commit or roll back. Nothing is ever destroyed: episodes are
append-only and archived facts stay visible to history/as-of views. See
[07 — Dream & evolution](07-dream-evolution.md).

## Design rules (the project's constitution)

- **Provider abstraction is sacred.** Only `app/llm_client.py` imports the OpenAI SDK; all
  provider specifics come from `.env`. Switching OpenAI ↔ corporate endpoint is config, not
  code. (The graph layer gets its Graphiti-shaped clients from `graph/providers.py`, which
  reads the same settings.)
- **Memory methods stay swappable.** Retrieval approaches (naive vector, contextual hybrid,
  graph, future LightRAG/HippoRAG) are meant to be interchangeable behind an
  ingest/query/update/inspect seam, each with its own pre-built store — enabling
  side-by-side comparison on the same corpus. The interface is being frozen from the
  working GraphRAG implementation, not designed up front.
- **Incremental, never rebuild.** New documents extend both stores in place.
- **Readable code over comments.** Small single-purpose modules, self-explanatory names;
  comments only where intent is non-obvious.
- **Ship in slices.** Each feature lands as the smallest working end-to-end slice.

## Where things run

- **Backend** — FastAPI on :8000; one process hosts the API, the pipeline, and (by default)
  auto-starts a local bundled FalkorDB server on :6399. Python 3.12.
- **Frontend** — Vite + React 19 on :5173; two views (chat, graph) in one SPA.
- **State on disk** — `backend/.chroma/` (vectors), FalkorDB's `falkor.rdb` (graphs, incl.
  saves), `backend/app/conversations.db` (chats), `backend/app/memory.md` (personal memory),
  `backend/.beliefs/*.md` (beliefs). All local, all gitignored.

## Reading path for a new developer

1. This page, then [04 — Backend tour](04-backend-tour.md) with the code open.
2. [05 — Expert pipeline](05-expert-pipeline.md) — the most important single file.
3. [06 — Graph memory](06-graph-memory.md) + [07 — Dream](07-dream-evolution.md).
4. Skim [08 — API reference](08-api-reference.md), then [09 — Frontend](09-frontend.md).
5. Run the [lab](10-testing.md) and step through a retrieval trace.

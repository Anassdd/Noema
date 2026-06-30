# Retrieval — the contextual vector base (the queryable memory)

This is the rest of `app/retrieval/` after contextualization: it turns contextualized
chunks into a **queryable memory** and answers questions from it, grounded and cited.

```
ingest:  PDF/Markdown ─▶ parse ─▶ chunk ─▶ contextualize ─▶ embed ─▶ store (Chroma)
query:   question ─▶ embed ─▶ [dense ‖ BM25] ─▶ fuse (RRF) ─▶ rerank? ─▶ top-k context ─▶ answer
```

**Input:** a question (`str`). &nbsp; **Output:** ranked `list[ScoredChunk]` (→ a grounded `Answer`).

## Modules

| File | Role |
|---|---|
| `store.py` | `VectorStore` — embed contextual chunks, upsert into **Chroma** (embedded, on-disk, no server/GPU). One collection per `domain_id`. Incremental. |
| `bm25.py` | `BM25` — pure-Python Okapi BM25 (keyword search). No dependency, no GPU. |
| `rerank.py` | Reranker seam — `off` / `llm` (RankGPT via the chat endpoint) / `endpoint` (hosted cross-encoder). Optional. |
| `search.py` | `search_trace()` / `search()` — dense + BM25 → **RRF fusion** → optional rerank. Returns every stage. |
| `answer.py` | `answer()` — assemble a source-cited prompt from the top chunks → grounded answer. |
| `ingest.py` | `ingest_pdf` / `ingest_markdown` — the one call that chains parse→chunk→contextualize→embed→store. |
| `base.py` | `ScoredChunk`, `RetrievalTrace`, `Answer` — the stable contract. |

## What we store per chunk

We **embed the contextual text** (`blurb + chunk`) but **store + cite the original chunk**:
```
id = chunk_id
embedding = vector(blurb + chunk)     # blurb improves the match (Contextual Retrieval)
document  = original chunk text       # what the LLM reads and what we CITE
metadata  = { context, doc_id, pages, section, domain_id }
```
BM25 indexes the same `blurb + chunk` text. The blurb is a findability aid; provenance
(`doc_id`, `pages`, `section`) is what the answer cites.

## How a query is answered (the stages)

1. **Embed** the question (same provider model as the chunks).
2. **Dense search** — cosine nearest in Chroma → `scores.dense`.
3. **BM25 search** — keyword match over the same chunks → `scores.bm25`. Catches exact
   terms (symbols, names, French technical words) that embeddings blur.
4. **Fuse with RRF** — `score += 1/(60 + rank)` across both lists; a chunk found by
   **both** rises. → `scores.rrf`.
5. **Rerank** (optional) — reorder the top candidates by true relevance (`llm` mode = one
   LLM call; `endpoint` mode = a hosted cross-encoder). → `scores.rerank`.
6. **Top-k context** → **grounded answer** constrained to those sources, with `[S#]`
   citations the user can verify against `doc + page`.

`search_trace()` returns all of this (`dense / bm25 / fused / reranked / final` + timings)
— that's what the lab's **Retrieval** page renders step-by-step.

## The seam (so the graph drops in later)
Everything depends on `ScoredChunk` and the `search()` contract. The graph layer becomes
**just another retriever** that returns `ScoredChunk`s and is fused in — no rewrite.

## Decisions / config
- **Vector store:** Chroma, persistent at `VECTOR_DIR` (default `backend/.chroma`).
- **Embedding model:** `settings.embed_model` (dev `text-embedding-3-small`; prod = the
  company endpoint model). Swappable via the provider abstraction; validate on the French
  corpus.
- **Reranker:** `RERANK_MODEL` + `RERANK_BASE_URL` enable the dedicated endpoint; otherwise
  `llm` mode works through the chat endpoint (no extra service). Default `off`.
- Everything keyed by `domain_id` (`"default"` now; multi-domain later).

## Tested
`tests/test_retrieval.py` (deterministic fake embedder, temp Chroma, mocked chat): store
round-trip, dense ranking, BM25 exact-term, RRF fusion + agreement, grounded answer
assembly. Run: `backend/.venv/bin/python tests/test_retrieval.py`.

## Not yet wired into the product
This engine + the **Retrieval lab page** prove it works. Still to do (next increments):
wire `/upload` → `ingest`, wire `/chat` → `search + answer` (behind a setting), render
citations in the React UI, and build the eval bench. See the build plan.

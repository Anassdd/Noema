# Contextual Retrieval — situating each chunk in its document

This is the **"contextualize"** step of the contextual vector base (`chunk →
contextualize → embed → BM25 → rerank`). It implements **Anthropic Contextual
Retrieval**: an LLM writes a short blurb situating each chunk within its parent
document, and that blurb is prepended to the chunk before it is embedded and
BM25-indexed.

**Input:** the document's Markdown (`str`) + its `list[Chunk]`. &nbsp;
**Output:** `list[ContextualChunk]` (each = blurb + chunk, with token + cache accounting).

```python
from app.retrieval import contextualize_chunks
ctx = contextualize_chunks(document_markdown, chunks)   # list[ContextualChunk]
ctx[0].text        # "<blurb>\n\n<chunk>" — the payload to embed + index
ctx[0].context     # just the blurb
ctx[0].chunk       # the original Chunk (provenance intact)
```

## Why

A chunk pulled out of its document loses context ("the model" — which model? "this
approach" — which?). Embeddings and BM25 then match it poorly. Prepending a one- or
two-sentence situating blurb fixes that. Anthropic's first-party result: **−49%**
retrieval failures (contextual embeddings + contextual BM25), **−67%** with a reranker.
This is the single highest-ROI upgrade in the retrieval stack — which is why it is built
before the graph layer.

## How it works

```
whole document (stable, cacheable prefix) ┐
                                          ├─▶ LLM ─▶ 1–2 sentence context ─▶ prepend to chunk
one chunk ─────────────────────────────────┘                                   │
                                                                                ▼
                                            ContextualChunk.text  =  context + "\n\n" + chunk
                                                          (this is what gets embedded + BM25-indexed)
```

- The call goes through `llm_client.chat` (provider abstraction) at `temperature=0`, so
  OpenAI on dev and the Azure-hosted endpoint in prod are a `.env` switch.
- The **document is placed first** in the prompt, identical across all chunks of that
  document — so repeated calls hit **automatic prompt-prefix caching**: OpenAI-compatible
  endpoints cache a prefix once it passes **~1024 tokens**, billing a hit at ~10% of input.
  The document is charged full price once (first chunk), then ~10% for the rest. The cached
  portion is surfaced as `Usage.cached_tokens` → `ContextualChunk.cached_tokens` (0 for docs
  under the threshold — which is why small docs show no caching and large ones show most of
  the prefix cached).
- The model answers in the **document's language** (a French paper yields a French blurb),
  which keeps the contextual text consistent for multilingual retrieval.

## The exact prompt
`PROMPT_TEMPLATE` is Anthropic's, with the document first:

```
<document> … </document>
Here is the chunk we want to situate within the whole document:
<chunk> … </chunk>
Please give a short succinct context to situate this chunk within the overall document
for the purposes of improving search retrieval of the chunk. Answer only with the
succinct context and nothing else.
```

## Cost & caveats

- **One LLM call per chunk.** Made cheap by the cached document prefix; still, a 100-chunk
  document is 100 calls — an **ingestion-time, one-time** cost (nobody is waiting on it).
- **Whole document per chunk** is Anthropic's method and is fine for a paper-sized
  document. For a very long document that blows the context window, situate the chunk
  against its **section** instead of the whole doc (future option).
- Default model is the configured **chat model** (cheap tier is fine for blurbs); override
  per call with `model=`.
- Sequential for now; **concurrency** is an easy later win for ingestion throughput.

## Output (`ContextualChunk`)

```python
cc.chunk            # the original Chunk (chunk_id, pages, section, …) — provenance preserved
cc.context          # the LLM's situating blurb
cc.text             # context + chunk — the embed / BM25 payload
cc.prompt_tokens, cc.completion_tokens, cc.total_tokens
```

## Tested
`tests/test_contextual.py` (mocked LLM — free, no network): prompt structure
(document-first, chunk wrapped, temp 0), blurb assembly onto the chunk, token accounting,
empty-context fallback, no-chunks. Run: `backend/.venv/bin/python tests/test_contextual.py`.

## Try it
The lab's **Contextualizer** page shows it live and on cached examples:
```
backend/.venv/bin/python -m streamlit run tests/lab.py     # -> Contextualizer
```

## Next in this package
`embed` (vectors via the provider) → `store` (embeddable vector index) → hybrid search
(dense + BM25) → cross-encoder rerank. See `NOEMA_MEMORY_SOTA.md` for the build order.

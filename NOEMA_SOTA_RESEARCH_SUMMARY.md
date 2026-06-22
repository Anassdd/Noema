# Noema — SOTA Research Summary

A consolidated record of the state-of-the-art findings from the research rounds
(Claude + Gemini cross-referenced, first-party lab sources prioritized). This is
the "what's SOTA and why" reference. For *what we decided to build*, see the
decision log; for *what to build now*, see the v1 build spec.

**Trust legend:** **(A)** first-party lab / peer-reviewed · **(B)** reputable
eng blog or well-cited preprint · **(C)** vendor self-reported / unreviewed.
**Evidence:** [TESTED] independently reproduced · [SELF-REPORTED] vendor's own ·
[CLAIMED] asserted/architectural.

---

## The headline

There is **no single benchmarked "best system."** SOTA is a set of proven
*components* you assemble and then validate on your own corpus. The components
below are each well-supported; the *assembly* is reasoned, not benchmarked —
which is exactly why the build includes its own eval/bench.

---

## 1. Ingestion & parsing

- **Docling (IBM, open-source)** — SOTA structure-aware parser for text-heavy
  docs. Keeps tables (TableFormer), math→LaTeX, reading order, page provenance.
  Core parsing = local vision models, **no LLM**. Runs locally (good for Azure).
  **(A/B), production-real.**
- **ColPali (vision route)** — SOTA for *visually dense* docs where layout carries
  meaning (complex tables, charts, diagrams, scans). Embeds page images as
  multi-vectors, late-interaction match. Costs: heavy storage, vision LLM at
  generation, **can't feed a graph**. **(B).**
- **Verdict for Noema:** Docling default (keeps the graph alive). ColPali = deferred
  parallel path for visual pages only, routed per-page if ever needed.

## 2. Chunking

- **Structure-aware chunking (Docling HybridChunker)** is mainstream SOTA: cut on
  structure, resize to the embedder's limit. **(B).**
- Key insight: the *cut* is low-leverage. The gains are in what comes after
  (contextualization). Don't chase fancier chunkers.

## 3. Retrieval base (the highest-ROI layer)

- **Anthropic Contextual Retrieval** — prepend an LLM blurb situating each chunk
  in its document, before embedding **and** BM25; pair with reranking.
  First-party tested: **−49%** retrieval failures (contextual embeddings +
  contextual BM25), **−67%** with a reranker added. Per-chunk LLM cost made cheap
  by prompt-caching the parent doc. **(A) [TESTED].** This is the single
  best-supported upgrade in the whole stack.
- **Hybrid search (dense + BM25, fused) + cross-encoder rerank** is the SOTA base
  pattern. Mirrors OpenAI's documented file_search recipe (query-rewrite →
  decompose → hybrid → rerank). **(A).**
- **Embedding models (mid-2026):** Gemini Embedding and Qwen3-Embedding lead MTEB;
  open-weight models now match commercial APIs. For a French corpus,
  Qwen3-Embedding-8B is a strong self-host option. MTEB scores are
  **[SELF-REPORTED]** — verify on your own corpus. Keep the embedder swappable.

## 4. Graph layer (multi-hop) — the substrate choice

- **HippoRAG 2** — SOTA multi-hop: Personalized PageRank over an LLM-built graph,
  passage + entity nodes. Beats dense RAG and Microsoft GraphRAG on multi-hop;
  far cheaper to index (9M vs 115M tokens on MuSiQue); no regression on simple Qs.
  Peer-reviewed (ICML 2025). **(A) [TESTED].** Weakness: not natively incremental.
- **Graphiti (Zep)** — SOTA for the *evolving* graph: native incremental entity
  resolution + **bi-temporal** conflict handling (valid-time / ingestion-time,
  invalidate-don't-delete). Retrieval solid, not the multi-hop champion. **(B).**
- **LightRAG** — lightest, fastest incremental updates, dual-level retrieval.
  Simplest to stand up; middle on both axes. **(B).**
- **"GraphRAG" naming:** the *category* = any graph-based RAG; *Microsoft GraphRAG*
  = one product (community summaries). HippoRAG is in the category, a different
  (stronger-for-multihop) implementation.
- **Verdict:** these three sit behind one swappable seam. **#1 bench test** —
  compare on retrieval + growth + cleaning, on your corpus. Start LightRAG
  (simplest), measure, upgrade.

## 5. Global / thematic layer

- **RAPTOR** (recursive summary tree) and **Microsoft GraphRAG community
  summaries** are SOTA for "themes across the whole corpus" questions. **(B).**
- **Deferred** — add only if the eval shows global questions failing.

## 6. Query loop & grounding

- **Query loop:** route → retrieve → rerank → generate → cite → verify.
- **Self-RAG** — reflection-token self-correction; measured **lowest hallucination
  rate (5.8%)** in a controlled comparison. **(B) [TESTED].**
- **CRAG (Corrective RAG)** — grades retrieval, fetches more on low confidence. **(B).**
- **SOTA query path = iterative**: retrieve → judge "enough?" → retrieve more if
  not. Simple upfront routing is the pragmatic v1 stand-in.
- **Grounding gate:** verify claims are supported before shipping. Tools:
  **LettuceDetect** (token-level), **Vectara HHEM** (cross-encoder), RAGAS
  faithfulness. Google's Check-Grounding API is the first-party precedent. **(A/B).**
- **Citations:** span-level attribution (**C²-Cite++**, WSDM 2026) beats
  document-level tags. **(A/B) [TESTED].**

## 7. Evolutive memory (the differentiator)

- **Pattern (SOTA direction):** append-only **episodic log** as source of truth +
  a derived semantic/graph store + a **background consolidation loop**
  (dedup → reconcile → consolidate → forget). Validated in direction by Anthropic
  "Dreams" and OpenAI "Dreaming" (both 2026 background-consolidation launches). **(A/B).**
- **Critical safety finding:** unchecked LLM self-consolidation **degrades memory
  below the no-memory baseline** ("Useful Memories Become Faulty…", UIUC/Tsinghua
  2026 — 54% of previously-solved problems failed). **(B) [TESTED].**
- **Therefore the safe SOTA design:** each consolidation pass = a **candidate**;
  an **eval gate** promotes only if it beats current memory, else rolls back;
  reversible (parallel artifact, Anthropic-style) not in-place (OpenAI-style);
  forgetting scored by recency × frequency × importance × centrality.
- **Entity resolution (growth):** two-tier — cheap embedding/string match → LLM
  only for the ambiguous middle. (Graphiti / ElephantBroker pattern.) **(B).**
- **Honest status:** named memory products (Mem0, MemOS, EverMemOS/EverOS, TiMem,
  MemoryOS) report strong numbers but are almost all **(C) [SELF-REPORTED]** with
  no independent reproduction, and benchmarks (LoCoMo, LongMemEval) aren't directly
  comparable across systems. **Adopt the pattern, not any vendor's benchmark.**

## 8. Multi-domain (deferred)

- **Isolate, don't merge** per-domain graphs (merging bloats + causes term
  collision). **(B).**
- **Router:** two-stage (fast semantic match → LLM fallback), `semantic-router`
  the named tool; go hierarchical (coarse→fine) as domains grow. **(B).**
- **Cross-domain questions:** parallel (query each, LLM merges) for independent
  Qs; sequential agentic chain (SCOUT-RAG direction) for dependent Qs. Frontier,
  least-proven. **(C).**

---

## What's genuinely TESTED vs reasoned (read this before trusting a number)

- **Solid (A)/[TESTED]:** Anthropic Contextual Retrieval (−49/−67%), Anthropic
  memory+context-editing (+39% / −84% tokens), HippoRAG 2 (ICML 2025), Self-RAG
  (5.8% hallucination), C²-Cite++ (WSDM 2026), the faulty-memory degradation finding.
- **Reasoned, not benchmarked:** the *assembled Noema stack* (contextual base +
  HippoRAG graph + RAPTOR + iterative loop + evolutive memory). No paper benchmarks
  this exact combination → your bench validates it.
- **Treat as marketing until reproduced (C):** all agent-memory product
  leaderboard scores (Mem0/MemOS/EverOS/TiMem/etc.).

---

## The v1 stack (what this research points to building first)

Single domain → **Docling** parse → **HybridChunker** → **Contextual Retrieval**
base (contextual embeddings + BM25 + rerank) → **graph layer starting on LightRAG**
→ **evolutive loop with an eval gate** (append-only log underneath).
Deferred, add when the bench demands: RAPTOR, ColPali, iterative Self-RAG loop,
multi-domain router, HippoRAG/Graphiti substrate swap.

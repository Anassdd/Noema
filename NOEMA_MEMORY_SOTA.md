# Noema — Memory Representation SOTA (verified findings)

A cited record of the deep-research round on **how to represent and store Noema's
domain-knowledge memory**, for the exact constrained case: a single-domain (later
multi-domain) expert over ~100 **French, math-heavy** research papers; **Azure-only /
no-GPU / in-tenant** prod (OpenAI-compatible endpoint, `.env`-only dev→prod); doc+page
**provenance/citation required**; **incremental + evolutive** (self-cleaning) memory.

**Method.** 107-agent fan-out web search → 25 sources → 125 extracted claims → **25
adversarially verified** (3 independent skeptics per claim; ≥2 refutes kills it).
Only verified results appear as findings; vendor numbers that failed are under *Refuted*.

**Trust legend:** `[VERIFIED 3-0]` unanimous · `[VERIFIED 2-1]` majority · `[REFUTED]` killed.

> **Scope note.** The verification budget concentrated on the contested graph-vs-vector
> benchmark question. Three angles were *searched* but did **not** reach the verified set —
> (5) French/math embedding specifics, (6) the big-chat-agents survey, and embeddable-store
> benchmarking. Those are the subject of a **follow-up round** (see the last section); do
> not treat them as settled from this document.

---

## Bottom line

The chosen **representation is right**, but the **graph layer is worth less than the
vendor hype** — so the plan's ordering "build the contextual hybrid base first, add the
graph as a *measured* upgrade" is strongly vindicated, and the "measure" step is now
non-negotiable. The **evolutive design** (append-only log + eval gate + bi-temporal) is
validated and feasible **API-only, no GPU**.

---

## Verified findings

### 1. Hybrid graph + vector over the *same* chunks is the correct representation `[VERIFIED 3-0]`
The SOTA systems are exactly "cooperating layers over one chunk set," not two corpora:
- **KET-RAG** indexes two cooperating structures over the same chunks — an LLM-extracted
  KG skeleton **plus** a text–keyword bipartite graph — and matches/beats Microsoft
  GraphRAG retrieval at a fraction of the indexing cost.
- **HippoRAG-2** integrates **passage** and **phrase** nodes via `contains` edges,
  retrieved with Personalized PageRank.

This *is* Noema's "one domain memory, two retrieval lenses" design.
Sources: [arXiv:2502.09304 (KET-RAG)](https://arxiv.org/pdf/2502.09304),
[arXiv:2502.14802 (HippoRAG-2)](https://arxiv.org/html/2502.14802v1)

### 2. HippoRAG-2 is the right multi-hop lens; LightRAG is the simpler/weaker bootstrap `[VERIFIED 3-0 architecture / 2-1 ranking]`
HippoRAG-2 ranks **citable source passages** by PageRank, so provenance falls out of
retrieval. The *ranking* advantage is benchmark-dependent (see finding 3), not absolute.
Source: [arXiv:2502.14802](https://arxiv.org/html/2502.14802v1)

### 3. ⚠️ The graph's real edge over plain retrieval is SMALL (~2 pts), and vendor "supremacy" is inflated by eval bias `[VERIFIED 3-0]`
On the independent **GraphRAG-Bench**: RAPTOR **73.58** vs BM25/TF-IDF **~71.7** vs a bare
LLM **70.68**; and HippoRAG **72.64**, LightRAG **71.22**, MS-GraphRAG **72.50** — all
clustered. An **unbiased-evaluation** paper found LLM-judge position/length/trial bias:
**LightRAG's win-rate vs naive RAG fell from 66.7% to ~39% once debiased.**
Implication: the contextual hybrid **base** does most of the work; the graph is a small,
**corpus-dependent** add-on — prove it on the real corpus before investing.
Sources: [arXiv:2506.02404 (GraphRAG-Bench)](https://arxiv.org/html/2506.02404v2),
[arXiv:2506.06331 (unbiased eval)](https://arxiv.org/pdf/2506.06331)

### 4. Evolution layer: distinct timestamped edges + bi-temporal invalidate-don't-delete + GATED consolidation — and it's API-only feasible `[VERIFIED 3-0]`
- Keep **distinct timestamped edges**, do **not** collapse history into one node (TG-RAG).
- **Graphiti** marks changed/conflicting edges **invalid, not deleted**, across an
  Episode/Entity/Community hierarchy (non-lossy).
- **Unchecked LLM consolidation degrades memory *below* the no-memory baseline**, while a
  plain episodic-retention control wins → consolidation must be **gated** (promote only if
  it beats current memory). This validates the append-only-log + eval-gate plan.
- **E2RAG** runs this evolution **API-only on LightRAG's index, no GPU** → fits the lockdown.
Sources: [arXiv:2510.13590 (TG-RAG)](https://arxiv.org/abs/2510.13590),
[arXiv:2501.13956 (Graphiti)](https://arxiv.org/abs/2501.13956),
[arXiv:2605.12978 (consolidation degradation)](https://arxiv.org/abs/2605.12978),
[arXiv:2506.05939 (E2RAG)](https://arxiv.org/pdf/2506.05939)

---

## Refuted claims (do NOT build on these)

| Claim | Verdict | Source |
|---|---|---|
| "HybridRAG concatenation beats both methods (0.96 relevance, 1.0 recall…)" | `[REFUTED 0-3]` | [arXiv:2408.04948](https://arxiv.org/html/2408.04948v1) |
| "HippoRAG-2 beats everything by ~7% across all memory tasks" (vendor self-report) | `[REFUTED 0-3]` | [arXiv:2502.14802](https://arxiv.org/html/2502.14802v1) |
| "Graph RAG **hurts** math/symbolic content" | `[REFUTED 0-3]` | [arXiv:2506.02404](https://arxiv.org/html/2506.02404v2) |
| "Graph excels extractive / vector excels abstractive" | contested `[2-1]` | [arXiv:2408.04948](https://arxiv.org/html/2408.04948v1) |
| "Graph's biggest win is multi-hop (RAPTOR +5.36 R)" | contested `[2-1]` | [arXiv:2506.02404](https://arxiv.org/html/2506.02404v2) |

Note the third row is **good news**: there is **no verified evidence the graph hurts a
math corpus** — but equally none that it strongly helps. Net: graph = measured add-on.

---

## What it means for the Noema plan

- **Keep** the hybrid-over-same-chunks representation — confirmed SOTA.
- **Keep** LightRAG-first → HippoRAG-2, but **recalibrate**: the contextual hybrid base
  carries the load; the graph is a ~2-point, corpus-dependent upgrade. The plan's
  "build base → **measure** → add graph" is exactly right and the measure step is mandatory.
- **Keep** the append-only-log + eval-gate + bi-temporal evolution — strongly validated,
  API-only feasible (no GPU, fits Azure-only lockdown).

---

## Coverage gap → follow-up round

Searched but **not** in the verified set (follow-up research in progress):
1. **French + math-heavy** representation/embedding (entity extraction in French,
   LaTeX/formulas as nodes vs text, multilingual embedding choice for the Azure endpoint).
2. **What the big chat agents actually use** (Claude / ChatGPT / Gemini / Perplexity /
   Copilot / Grok) and the agent-memory frameworks (Mem0, Letta/MemGPT, Zep/Graphiti,
   LangMem, MemOS) — and the frontier trend.
3. **Embeddable, Azure-safe storage** (Kùzu, SQLite-graph, DuckDB, NetworkX, Chroma,
   LanceDB, pgvector vs server-based Neo4j/Qdrant) — what embeds vs what needs a server.

This document will be updated when those land.

# Noema — Build Decision Log

A distilled record of the design decisions, in the order the questions came up.
Not a transcript — the gist of each question and the call we landed on.
Grouped into stages for readability; numbering preserves the original order.

**v1 in one line:** single domain → Docling parse → HybridChunker → contextual hybrid retrieval base + a graph layer (start LightRAG) → evolutive self-cleaning loop with an eval gate. Everything else (RAPTOR, ColPali, iterative retrieval, multi-domain router) is a measured upgrade for later.

> **Update (2026-06-22):** the *parse* step changed — parsing now runs on a hosted, `.env`-swappable backend (Azure vision / Document Intelligence), with Docling kept as a local fallback. Rationale in the Stage B revision note below.

---

## Stage A — Scope & overall shape

### 1. Domain scope: single-domain first
Build one expert first; multi-domain is a **router bolted on later**, not a rewrite.
- **Do now:** tag everything (retrieval, graph, episodic log) with a `domain_id`. Phase 1 always uses one value (`"default"`).
- **Later:** isolated per-domain graphs + a router that picks the `domain_id`. Experts don't change; they get *selected*.
- Rationale: the hard work is identical for 1 domain or 10. Routing is a separate, later problem.

### 2. Ingestion pipeline shape (100 static PDFs → memory)
Four moves: **parse → chunk → extract → store.**
- **Parse:** PDF → clean structured text.
- **Chunk:** passages, each tagged with provenance (doc + page) for citations.
- **Extract:** pull entities + relationships → builds the knowledge graph (graph route only; plain RAG skips this).
- **Store:** embeddings in the vector DB, graph in the graph store — both keyed by `domain_id`.
- **Note:** the *evolutive* loop (prune/consolidate/forget) is **separate and later** — only matters once memory grows. Not needed while 100 PDFs sit static.

---

## Stage B — Parsing the PDFs

> **Revision (2026-06-22) — parsing moves to a hosted, `.env`-swappable backend.**
> The original choice below (local Docling) assumed running parse models locally was
> the lockdown-friendly option. Two facts changed that: (a) prod runs on locked-down
> **company PCs that have only Azure models and restricted installs** — they likely
> can't install/run Docling's torch models; (b) with local Docling, ingestion
> quality/speed is **hostage to the machine** — weak PCs can't do it, or do it badly.
> So the default flips to **Azure-hosted parsing**, which keeps data in the Azure
> tenant *and* offloads the heavy compute (any PC, however weak, gets the same result).
>
> **New shape — a `Parser` provider seam (mirrors `llm_client`), chosen by `.env`:**
> - **Azure OpenAI vision** (default candidate): render each page locally to an image
>   (cheap, no model) → the vision model returns Markdown + LaTeX. Reuses the existing
>   LLM provider abstraction, so Mac→prod is the *same* `LLM_PROVIDER` `.env` switch
>   already used for chat. One call covers OCR + layout + tables + formulas — validated
>   on a real corpus file (`resume_af.pdf`: broken-font French math needed all four).
>   Frontier VLMs benchmark ~9.6 on formula extraction, near Mathpix.
> - **Azure Document Intelligence** (alternative): send the PDF, get structured output
>   + LaTeX formulas; stays in-tenant; zero local compute; less hallucination-prone
>   than a chat-vision model.
> - **Docling (local)**: kept as a **config-selectable fallback** — for offline /
>   air-gapped boxes or a strong dev machine. No longer the assumed default. Empirical
>   finding: Docling's standard pipeline leaves formulas as `<!-- formula-not-decoded -->`
>   unless the (heavy) CodeFormula model is enabled.
> - Third-party APIs (Mathpix, Marker, Mistral OCR) are best-accuracy but **send data
>   out** → dev/eval only, never prod.
>
> Carried-forward question: does the company Azure expose a **vision-capable** model
> and/or **Document Intelligence**? That picks the prod default.

### 3. Parse step: use Docling
IBM's open-source parser. Chosen because it:
- Keeps structure (tables, sections, formulas) instead of flattening to raw text.
- **Retains page provenance** — required for citations.
- Runs **locally** — good for the locked-down Azure target.
- Handles embedded images/figures (classify + caption via a vision model).
- Digital PDFs: excellent. Scanned: works via **OCR**, enabled only when needed.
- Upgrade over the current app's `pypdf` (which dumps raw text, chokes on tables/scans).

### 4. Parsing approach — where Docling sits vs SOTA
- **Parse-then-chunk (Docling):** best for **text-heavy** corpora. Fast, cheap, citable, local. → default.
- **Vision-based (ColPali):** embeds each page as an image; best when **layout carries meaning**. Heavier, harder to cite.
- **Call:** Docling default; ColPali later as a *parallel path behind the same parse seam* for genuinely visual docs.

### 7. Docling vs ColPali (the parse fork)
- **Docling (text):** wins for text docs. Citable to spans, light, **graph-friendly** (graph needs text).
- **ColPali (vision):** wins when layout carries meaning — complex pages, charts/diagrams, scans. No parsing errors.
- **ColPali costs:** heavy storage (many vectors/page), more query compute, citations point to a page-*image*, and it's **hard to build a graph from**.
- **One-liner:** documents visual → ColPali; documents text → Docling. Noema default = Docling.

### 8. The ColPali pipeline (if taken) — no chunk/context step
Replaces parse→chunk→contextualize: **render** page → **embed** as patch vectors (multi-vector) → **store** in a multi-vector DB (e.g. Qdrant) → **query** via late-interaction match. No chunking, no BM25; rerank is built into the scoring.

### 9. If doing both (Docling + ColPali) — how to route
- **Route per page, not per PDF.** Docling on everything; *also* ColPali-embed diagram-dense pages. Query searches both.
- Detection is free: Docling reports text-vs-visual per page.
- **But** two indexes + fusion = complexity. **v1 = Docling only.** Add ColPali later only if eval shows diagram questions missed.

### 21. ColPali instead of embedding — what changes (decided: Docling first)
- **Changes ingestion+retrieval:** no parse/chunk/context/BM25 → render → embed patches → store; retrieval = visual late-interaction.
- **Breaks the graph layer:** graph substrates need **text** for extraction; ColPali gives images → no graph → loses the multi-hop thesis (unless you also run text extraction = both pipelines).
- **Survives:** query loop shape, citations (to page images), multi-domain routing, cleaning concept.
- **Decision:** build the **Docling text method first**; ColPali revisited later as the optional parallel visual path. Pure-ColPali = giving up the graph.

---

## Stage C — Chunking & the retrieval base

### 5. Chunk step: Docling HybridChunker
Built-in, the right default. Cuts on real structure (sections/paragraphs), resizes to the embedding model's limit (merge too-small, split too-big), keeps provenance.
- One knob: target chunk size (~500–1000 tokens to start; tune later).
- The chunk *cut* is low-leverage; the gains are in what you do after (contextual retrieval).

### 6. Retrieval base: the SOTA stack (text-heavy)
Four layers, not one trick:
1. **Chunk** — HybridChunker (the cut).
2. **Contextualize** — prepend an LLM blurb situating each chunk in its document, before embedding *and* BM25. (Anthropic Contextual Retrieval — their actual contribution.)
3. **Hybrid search** — embeddings + BM25 fused. Not vectors alone.
4. **Rerank** — cross-encoder reorders top candidates before the LLM.
- Measured (Anthropic, first-party): −49% retrieval failures (2+3), −67% (add 4).
- Cost: step 2's per-chunk LLM call made cheap by prompt-caching the parent doc.
- Note: "contextual" = situating a chunk in its own document. Separate from the evolutive-memory loop.

---

## Stage D — Retrieval architecture (the graph layer)

### 10. Layers for question types (the SOTA shape)
Not "graph vs vector" — **cooperating layers**, one per question type:
1. **Contextual hybrid base** → **single-fact** questions. Near-SOTA already.
2. **HippoRAG-2 graph layer** (entities + relationships + PageRank) → **multi-hop** across docs. Uses the base's embeddings for entry points, so the base is permanent.
3. **Summary layer (RAPTOR / community summaries)** → **global / thematic**. **Deferred** until eval shows global questions failing.
- **v1 = layers 1 + 2.** Build base → measure → add graph → measure.

### HippoRAG, explained
A knowledge graph + spreading activation. Ingestion: LLM extracts `(A)—relationship—(B)` triples per chunk → assembled into one graph, nodes remember their chunks. Query: find entry-point nodes (embeddings) → run **Personalized PageRank** to flow outward and light up connected entities several hops away → retrieve their chunks. Wins multi-hop because it connects facts no single chunk states. "2" = better passage integration + LLM filtering, so it no longer hurts on simple questions.

### "GraphRAG" naming
Two meanings: (1) the **category** = any graph-based RAG; (2) **Microsoft GraphRAG** = one specific product (community summaries). HippoRAG is in the category, but is a *different, competing* implementation from Microsoft's — and the stronger pick for multi-hop. Monitor's "show GraphRAG" = the category; HippoRAG satisfies it.

### 11. Cost & latency — where it actually lives
- **Ingestion (one-time, offline):** graph extraction = 1 LLM call/chunk. Real but one-time, nobody waiting. Contextual blurb here too, cheap via prompt caching.
- **Query time:** layers are **options selected per question, not stacked**. PageRank is cheap (no LLM). Only real query cost = the answer-generation LLM call.
- **Myth busted:** 3 layers ≠ 3× slow — they're routed.
- **Move:** measure ingestion on ~5 PDFs before scaling to 100.

### 12. Query loop + method status (settled direction)
**Two worlds:** ingestion builds the library; query time answers from it.
**Query loop:** find → rerank → generate → cite → verify.
- **Simple routing (v1):** classify question → use the fitting layer once.
- **SOTA (later):** iterative Self-RAG/CRAG loop — retrieve, judge "enough?", pull more only if needed. Not all layers every time.
- **Proof status (honest):** components are SOTA-backed — Contextual Retrieval (−49/−67%), HippoRAG 2 (ICML 2025, beats vector + MS GraphRAG on multi-hop), Self-RAG (lowest hallucination 5.8%), CRAG, RAPTOR. **The assembled whole is reasoned, not benchmarked → that's what the bench validates.**
- **Method = settled:** v1 = contextual base + HippoRAG-2 graph + simple routing + grounding check. Deferred = RAPTOR, iterative loop, ColPali.

---

## Stage E — Growth & self-cleaning (the evolutive thesis)

### 13. Growth (inserting new docs) + entity resolution
- New doc → same pipeline → **merge into the graph, not rebuild** (incremental update).
- Hard part = **entity resolution**: link "COX-2" ≡ "Cyclooxygenase-2", don't merge "Mercury" planet vs element. Where graph quality lives.
- **SOTA pattern = two-tier:** cheap embedding/string match first → LLM only for the ambiguous middle. (ElephantBroker / Graphiti.)

### 15. Self-cleaning loop
Background worker (never blocks users): **dedup → reconcile conflicts → consolidate → forget** (forget scored by recency × frequency × importance).
- **Additive** — does NOT change retrieval. A background job + an **append-only episodic log** (source of truth) underneath.
- **Safety (critical, from research):** LLM self-rewriting can rot memory below no-memory. So: log append-only & never mutated; each pass = a **candidate**; an **eval gate** promotes only if better, else rolls back. Reversible, not in-place.
- **Native-ness depends on substrate:** Graphiti = mostly built-in; HippoRAG = build it yourself; LightRAG = partial.

---

## Stage F — The graph substrate choice (the #1 test)

### 14 + 16. The three candidates, two axes
| | Multi-hop retrieval | Evolves/cleans | Simplicity |
|---|---|---|---|
| **HippoRAG-2** | best | weakest | medium |
| **Graphiti (Zep)** | good | best (native bi-temporal) | medium |
| **LightRAG** | medium | good | best |
- Graphiti = a **candidate implementation of the graph layer** (same seam as HippoRAG), not a separate memory.
- **Start with LightRAG** — simplest to prove the whole pipeline, good enough on both axes.
- Optional later: LightRAG/Graphiti for the evolving graph + export to HippoRAG for retrieval = both strengths, two systems. Not v1.

### 17. Substrate bench-test spec (the #1 decision)
Test all three on **three jobs**:
- **Retrieval:** simple-Q accuracy, multi-hop accuracy.
- **Growth:** clean merge vs duplication, entity-resolution quality, add speed/cost.
- **Cleaning:** conflict handling, stays compact vs bloats, native vs build-it.
- **Order:** build pipeline on one (LightRAG) → get bench working → swap others → compare. Not all-three-upfront.

---

## Stage G — Memories & multi-domain

### 19. Two memories — keep separate (decided)
- **User memory** (`memory.json`, already built) = facts about the *person*. Small, injected into every prompt.
- **Domain memory** (knowledge graph) = what the system knows about the *field*. Large, retrieved when relevant. Keyed by `domain_id`.
- **Keep fully separate** — different content/size/lifecycle/retrieval. Leave `memory.json` untouched.
- **They meet only at prompt assembly:** user facts as personal context + retrieved domain facts as knowledge → one prompt, two sources, no contamination.
- Later "save conversation into knowledge" = a gated promotion into domain memory, not a merge.

### 20. Multi-domain (Phase 3 — deferred, shape only)
**Combine = isolated experts + a router. Never merge memories** (merging bloats + term-collision).
- Each domain = sealed expert (own graph/memory, keyed by `domain_id`).
- **Router (SOTA):** two-stage (fast semantic match → LLM fallback); **hierarchical** (coarse→fine) as domains grow.
- **Cross-domain question (one Q → several experts):**
  - Single-domain → one expert (most questions).
  - Independent cross-domain → **parallel**: query each, an LLM merges. Simple, fast. v1 choice.
  - Dependent cross-domain → **sequential chain**: A answers → B gets question + A's answer → … → final. Better for interconnected Qs; SOTA/agentic direction (SCOUT-RAG). Slower, pricier. Knobs: order, when-to-stop, cost.
- **SOTA sequencing:** build ONE strong expert first; router drops in cleanly later because everything's keyed by `domain_id`.

---

## Stage H — Parked / still to detail

### 18. Parked
- **Grounding gate + citations** (output anti-hallucination side): verify each answer is supported before it ships; attach doc+page sources. Touched, not detailed — figure out later.
- **The bench** (eval set + runner): the measuring tool that makes every "we'll test it" real. Plan's Increment 0 — revisit when building starts.

### Open questions (next decisions)
- **Corpus profile:** are the 100 PDFs mostly text, or genuinely visual? → decides whether ColPali ever matters.
- **Multi-domain timing:** real near-term goal or someday-maybe? → decides router effort.
- **Grounding gate mechanism:** which verifier (HHEM / LettuceDetect / Self-RAG-style) when we detail it.

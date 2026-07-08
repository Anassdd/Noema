# NOEMA_EVAL_BENCH — the benchmark plan: methods, datasets, axes, dream harness, costs

*2026-07-06. The frozen design for comparing memory methods head-to-head, and for measuring
Dream (auto-evolution) as a lift. Companion to
[NOEMA_EVOLUTION_CONTRACT.md](NOEMA_EVOLUTION_CONTRACT.md) — the contract says WHAT
evolution must respect; this file says WHERE and HOW everything gets measured, and what it
costs on a personal API key.*

---

## 0. Budget reality (read first)

All testing runs on a **personal OpenAI key with a limited budget**. Every decision below
is shaped by that. The hard rules:

1. **Set a hard usage limit on the OpenAI dashboard** before the first run. Pick the
   monthly cap you can actually afford; the bench is designed to fit in stages under it.
2. **Nothing large runs before its pilot.** Every corpus gets a ~100k-token paid pilot
   (~$8); read the real cost off the dashboard, multiply by corpus size, and only then
   commit. This turns ±2× estimates into ±10% facts.
3. **Indexes are assets, not runs.** Build once, checkpoint with the saves system, restore
   forever. All query-side experiments reuse the same paid index. Ingestion settings
   (chunker, extractor model, schema) must be FINAL before a build — changing them means
   paying for the build again.
4. **Cheap runs first.** Closed-book control and base-alone cost dollars; graph indexing
   costs hundreds. The execution order (§9) is sorted by spend, with a go/no-go gate
   before each paid tier.
5. **Record spend per experiment**: dashboard reading before/after each build and each
   query batch, written into the run's result file. Cost is itself a benchmark criterion
   (axis 6) — the receipts ARE data.
6. **Expensive datasets are deferred, not dropped**: FinanceBench full corpus and
   LongMemEval belong to a corporate-budget phase (§8, §9).

---

## 1. What we compare — methods and configs

Memory methods, staged:

- **Phase A (built today):** Contextual RAG (Anthropic-style hybrid dense+BM25 over
  situated chunks) · Graphiti (temporal knowledge graph) · Graphiti+Contextual (the
  product).
- **Phase B (to integrate):** NaiveRAG · LightRAG · GraphRAG (Microsoft) · HippoRAG.

Each graph method runs **alone** and **+ contextual base** (same RRF fusion), plus two
controls:

| # | Config | Role |
|---|--------|------|
| 0 | Closed-book (generator, NO retrieval) | contamination floor — Wikipedia benchmarks are in training data; every score counts only from this floor up |
| 1 | Contextual RAG alone | the control every lift is measured against |
| 2–5 | each graph alone | is the graph pulling weight or riding the base? |
| 6–9 | each graph + base | the product configs |

**Configs share indexes.** ±base is a *query-time* change: one vector index + one graph
index per (method, corpus) serves both the alone and the hybrid config. 10 configs ≠ 10
builds — per corpus it is 1 vector build + 4 graph builds.

**Why the "alone" runs matter:** if Base+Graph ≈ Base alone, the graph is decoration; if
Graph-alone is weak but Base+Graph wins, fusion is doing real work. The two hybrids alone
cannot distinguish these.

**Each method's design bet** (the axes in §4 give each one a home turf):

- GraphRAG → corpus-level sensemaking (Leiden communities + pre-written summaries).
- LightRAG → cheapness + dual-level (entity-level and theme-level) retrieval.
- Graphiti → time (episodic ingestion, entity resolution, contradiction invalidation).
- HippoRAG → association (Personalized PageRank as a one-shot multi-hop passage ranker).

**GraphRAG special case:** its *global* mode returns a generated answer, not retrievable
items — it cannot be RRF-fused. Fused configs use **GraphRAG local search**; global mode
is evaluated separately, only on the sensemaking axis.

---

## 2. Frozen model set (one per role, pinned snapshots, temp 0)

### Verified pricing (July 2026 — OpenAI pricing page + provider comparisons)

| Model | $/1M input | cached input | $/1M output | Note |
|---|---|---|---|---|
| gpt-5.5 | 5.00 | 0.50 | 30.00 | flagship — never needed here |
| gpt-5.4 | 2.50 | 0.25 | 15.00 | reference extractor for the quality spot-check |
| **gpt-5.4-mini** | 0.75 | 0.075 | 4.50 | the workhorse |
| gpt-5.4-nano | 0.20 | 0.02 | 1.25 | budget generator arm |
| gpt-4.1-mini (app default until 2026-07-06) | 0.40 | — | 1.60 | ⚠ **deprecates 2026-11-04 — never pin anything to it**; app defaults moved to gpt-5.4-mini (chat) + gpt-5.4 (parse/extract) |
| text-embedding-3-large | 0.13 | — | — | unchanged |
| Gemini 3 Flash | 0.50 | — | 3.00 | cross-family judge |
| Gemini 3.1 Flash-Lite | 0.25 | — | 1.50 | cheaper judge option |
| DeepSeek V4 Flash | 0.14 | — | 0.28 | cheapest capable API; OpenAI-compatible |
| Mistral Small 3.2 | 0.10 | — | 0.30 | GDPR-friendly budget option |
| **MiniMax M2** (M2.1/M2.7 newer) | 0.30 | — | 1.20 | **budget extractor candidate**: 230B MoE / 10B active, open weights, ~205k ctx, OpenAI-compatible (own platform + OpenRouter). Extraction ≈ $10–13/1M corpus tokens ⇒ all 3 domains ≈ $13–16. Two pilot gates: extraction quality (A2 spot-check) + interleaved-thinking output must not break Graphiti's JSON parsing. Open weights fit ONE MI300X ⇒ also the best AMD self-host extractor. Chinese provider: public corpora only, never BNP docs |

Two discounts that change the math:

- **Prompt caching: cached input −90%**, automatic on shared prefixes >1k tokens.
  Graphiti's repeated prompt scaffolding partially caches during continuous ingestion.
- **Batch API: −50%**, for everything embarrassingly parallel — closed-book run,
  gold-question generation, judging. **Not** Graphiti ingestion (each episode depends on
  the graph state before it — sequential by nature).

### The roles

| Role | Choice | Why |
|---|---|---|
| Extractor (builds ALL graphs) | `gpt-5.4-mini` | 2026 mini-tier ≈ 2025 full-tier capability at 1/3 the token price. Same extractor for all four graph methods — extraction quality is a constant, not a variable. **A2 pilot includes an extraction spot-check**: build 20 pages with gpt-5.4-mini vs gpt-5.4, compare node/edge counts + eyeball quality; if visibly sparser, upgrade the extractor and re-gate the budget |
| Generator (the whole pipeline: route/grade/answer/verify) | `gpt-5.4-mini` default · `gpt-5.4-nano` or **local Qwen** as budget arms | deliberately non-flagship: a strong generator papers over bad retrieval and compresses method differences. Never `gpt-4.1-mini` (dies mid-bench) |
| Judge (long-form scoring) | **Gemini 3 Flash** (cross-family) | a judge from a different family than the generator kills self-preference bias; always gold-anchored + position-swapped; judging is small tokens (~$5–15 total) so family diversity is nearly free |
| Embeddings (everything) | `text-embedding-3-large` | $0.13/M is noise; one embedder for base, Graphiti, HippoRAG, LightRAG — or retrieval differences become embedding differences. Local embedders (bge-m3, Qwen3-Embedding) would save ~$2 total — not worth adding a variable; revisit only if French quality demands it (Tier-2) |

Pin snapshot IDs, never floating aliases. If the model set changes, every earlier number
is dead. All external methods and all listed providers accept OpenAI-compatible endpoints,
so one config serves everything. Numbers on the prod llmaas models would be a full re-run —
decide which endpoint's numbers you present BEFORE burning the indexing budget.

### The local (free) option — M2 Pro

Ollama serves an OpenAI-compatible `/v1`, and Noema's provider seam means local inference
is **a `.env` change, zero code** (point the llmaas provider at
`http://localhost:11434/v1`).

- **16 GB M2 Pro** (the user's machine): **Qwen 3.5 9B** (Q4 ≈ 6.6 GB — best
  reasoning/IF in class, multilingual, leaves KV-cache headroom for context-heavy RAG
  prompts); runner-up Gemma 4 E4B (multilingual champion). Pick empirically: 20-question
  bake-off in A0, judged against gold + JSON reliability — free. 14B-class (Phi-4) is out:
  weights eat the RAM headroom that long retrieved contexts need.
- **32 GB M2 Pro**: Qwen 3.6-35B-A3B MoE (≈20 GB file, 3B active params → fast tokens).
- MLX-LM instead of Ollama when you want max Metal throughput; llama.cpp for brand-new
  models MLX lags on.

Rules for local:

- **Sanctioned for the GENERATOR role only.** Method *rankings* stay valid (same generator
  for every method); absolute numbers won't transfer to prod — label local-arm results
  clearly and keep them out of any table shown as "prod-expected".
- **Never for extraction.** Quality is load-bearing (weak extractor ⇒ sparse graph ⇒ you
  benchmark extraction tolerance, not methods) and the ~20× token amplification means
  weeks of Mac wall-clock.
- The real local win beyond $0 queries: **unlimited free reruns while debugging the
  harness** (A0–A1 can iterate locally without touching the budget) and overnight query
  batches (~3k answers ≈ one night at 30–60 tok/s).
- DeepSeek V4 Flash ($0.14/$0.28) is the API middle ground if local is too slow — but a
  third provider only enters if the pilot shows it matters.

### Free-compute lanes (verified 2026-07-06)

- **AMD Developer Cloud** — $100 free credits (~50 h) on MI300X (192 GB) for AI Developer
  Program members (apply early, approval not instant). vLLM serves an OpenAI-compatible
  API → same `.env` switch. **Big enough to run a Qwen-72B-class extractor** — the one
  role local can't cover; if it passes the A2 20-page spot-check vs gpt-5.4, extraction
  becomes $0 AND reproducible forever (open weights never deprecate). Math+CS extraction
  fits in a few of the 50 free hours.
- **Google AI Studio** — 1,500 req/day free Gemini Flash → the judge for $0.
- **Mistral Experiment tier** — ~1B tokens/month free but **opt-in to data training**:
  public benchmark corpora only, categorically never BNP documents (rule applies to every
  free tier).
- **Cerebras** (~1M tok/day, 70B-class) / **Groq** (100K tok/day) — query-side and smoke
  tests; too rate-limited for extraction.
- Net: a legitimate $0–10 Math+CS bench = MI300X extraction (spot-check-gated) + local
  Mac queries + free Gemini judging; the OpenAI path stays the fallback if the 72B
  spot-check disappoints.

---

## 3. The dataset suite

### Tier 1 — the fixed core

| # | Dataset | Domain | Unique contribution | Gold? |
|---|---------|--------|---------------------|-------|
| D1 | **MuSiQue + 2WikiMultiHopQA + HotpotQA** (HippoRAG-style subsets) | Wikipedia: politics, history, general | multi-hop association, hop-tagged (2/3/4); comparability with published HippoRAG/GraphRAG numbers | answers + gold passages |
| D2 | **UltraDomain — CS, Legal, Math, Mix** ← **FIRST PRIORITY (2026-07-06)** | college textbooks: CS, math, law | long-document global sensemaking; LightRAG's own benchmark (verdict below) | corpora yes; queries LLM-generated, no gold answers → gold Qs are OUR prerequisite |
| D3 | **FinanceBench (open 150) + ConvFinQA (~200 sample)** | SEC filings, financial reports | banking realism: numeric lookup, multi-turn numeric reasoning, unanswerables (GPT-4-Turbo+retrieval failed >80%) | expert answers + evidence |
| D4 | **QASPER (~150–200 sample)** | NLP research papers | the papers domain with **gold evidence spans** → cleanest retrieval-recall measurement | answers + evidence |
| D5 | **MultiHop-RAG** | dated news | 4 query types: inference / comparison / **temporal** / **null** (hallucination probe); timestamps ⇒ date-ordered ingestion ⇒ doubles as a dream stream | answers + evidence + timestamps |
| D6 | **LongMemEval (S)** | multi-session conversation | THE dream benchmark: knowledge updates, temporal reasoning, abstention, multi-session joins — **deferred to corporate budget** (each question carries a ~115k-token history; graph-ingesting it is $100s) | 500 curated questions |

### Tier 2 — later / in-house

- **EUR-Lex / Légifrance amendment stream** — regulation + its amended versions ingested
  in order: the banking-grade supersession corpus, **and French**; we author ~40 probes.
- **BNP URD multi-year** — same design, internal corpus.
- **T²-RAGBench / FinRAGBench-V** — table-heavy/multimodal finance, once table parsing is
  a first-class concern.
- **Skipped: LoCoMo** — same ground as LongMemEval, contested published numbers.

Domain coverage: research papers→D4 · math→D2 · CS→D2 · politics→D1,D5 · law→D2,Tier-2 ·
conversation→D6 · stocks/finance→D3,D5 · French→Tier-2 only. **The French gap**: all
Tier-1 sets are English; add a ~30-question in-house French probe set (EUR-Lex French
versions) that measures degradation vs English only, never method ranking.

**Math note:** no good "RAG over math" benchmark exists — math benchmarks (GSM8K/MATH)
test the model's reasoning, not the memory. UltraDomain's Math textbooks (questions
*about* mathematical content) are the honest coverage.

### Verdict on LightRAG's dataset (UltraDomain)

**Keep the corpora, don't trust the scoreboard.** The published table is pairwise
LLM-judge win-rates on comprehensiveness/diversity/empowerment — no gold answers. LLM
judges reward longer answers (verbosity bias), suffer position bias, and those criteria
structurally favor panoramic graph summaries. 83.6% vs 16.4% means "the judge preferred
its style", not "5× more correct". What we do: generate ~100 gold-answerable questions
per subset from the textbooks (evidence spans, one manual verification pass), score those
as primary; keep the win-rate protocol only as a clearly-labeled secondary lens,
position-swapped and length-controlled. Also: it is static — useless for the dream axis.

**UltraDomain-first practicalities** (source: `huggingface.co/datasets/TommyChien/UltraDomain`,
verified 2026-07-06):

- 20 domain files exist, incl. `cs.jsonl`, `legal.jsonl`, **`mathematics.jsonl`**,
  `mix.jsonl` — and, bonus for later, **`fin.jsonl`** and **`politics.jsonl`** (finance +
  politics coverage from the same source, zero new plumbing).
- The jsonl rows are QA pairs each carrying their long context; the **corpus is built by
  extracting the UNIQUE contexts** (what LightRAG did), then capping at 400k tokens/subset
  by sampling whole documents.
- **Gold questions are the prerequisite**: no gold answers ship with it. Generate ~100
  answerable Qs/subset from the sampled documents (with evidence spans, Batch API), then
  one manual verification pass — before any index is built.
- Closed-book floor should be LOW on textbooks (unlike Wikipedia sets) — cleaner lift
  measurement, another reason it's a good first arena.

---

## 4. The six axes (one home turf per method bet)

| Axis | Question | Dataset | Should win on paper |
|---|---|---|---|
| 1. Factoid / local QA | do graphs help or hurt simple lookups? | D4, D3 | base alone |
| 2. Multi-hop association | who connects scattered facts? (by hop count) | D1 | HippoRAG |
| 3. Global sensemaking | "main themes of the corpus?" | D2 + our gold Qs | GraphRAG, then LightRAG |
| 4. Temporal correctness | stale-fact rate after supersession | D5 date-ordered, Tier-2 streams | Graphiti |
| 5. Incremental update | $ + quality drift to add ONE doc | any corpus, reused | Graphiti; GraphRAG should lose badly |
| 6. Cost / latency / storage | $/1M tokens indexed, query p50/p95, disk | free from all runs | LightRAG (its whole claim) |

Cross-cutting on every axis (measurements, not axes):

- **Citation quality** — can the answer cite doc + page? Structural per method: Graphiti
  keeps episode provenance, HippoRAG ranks real passages, GraphRAG global answers from
  community summaries barely cite. For Noema citations are a product requirement — a
  method that wins accuracy but can't cite may be unusable.
- **Abstention** — null/unanswerable queries (D5 nulls, D3 unanswerables): more retrieval
  sources ⇒ more plausible context ⇒ more temptation to answer. False-answer rate.

The endpoint deliverable is a **method × axis grid of lifts over base-alone**. On-diagonal
cells confirm the papers; the off-diagonal cells (GraphRAG's stale-fact rate, HippoRAG's
sensemaking…) are the unpublished findings — "each is perfect for what, and why" lives
there.

---

## 5. Metrics

- **Correctness**: EM/F1 where gold short answers exist (D1, D5); numeric-with-tolerance
  (D3); rubric LLM-judge against gold for long-form (D2, D4).
- **Abstention quality**: false-answer rate on unanswerables.
- **Retrieval (diagnostic)**: evidence recall@k / precision@k vs gold passages; context
  efficiency (tokens of context needed to reach the answer).
- **Groundedness**: citation precision (does `[S1]` support the sentence citing it —
  sample ~50/dataset, claim-vs-source judged).
- **Sliced, not averaged**: by hop count (D1), by query type (D5), by memory ability (D6).
- **Temporal**: current-fact accuracy after supersession (plain RAG's published stale rate
  is 15–40% — the number Graphiti must crush) + historical accuracy ("true in 2022?").
- **Fusion diagnostics** (trace-level, we already stream traces): fraction of fused top-k
  from the graph side; accuracy conditioned on graph items present — separates
  *contributor* / *redundant* / *contaminant*. Prediction to test: HippoRAG+base cleanest
  synergy; LightRAG+base largely redundant with the contextual base; GraphRAG+base
  complementary but awkward.
- **Cost/ops**: indexing $ and wall-clock per 1M corpus tokens; $ to add ONE document to
  an existing index; query latency p50/p95; tokens/query; index size on disk.
- **Secondary lens only**: UltraDomain-style win rates, position-swapped,
  length-controlled, reported last and labeled as stylistic preference.

---

## 6. Fusion fairness rule

Graphiti returns facts, HippoRAG passages, LightRAG mixed items — granularity differs. For
headline numbers, fuse each method's *native* output (as its authors intended) and
acknowledge the asymmetry; as a sanity check, force all methods to rank the same chunk set
(via provenance) — if the ranking flips, granularity was the real variable, not the graph.

---

## 7. The Dream (auto-evolution) harness

Dream fixes diseases a fresh memory doesn't have — duplicates, superseded facts, bloat
accumulate over a **stream**. Testing it on a one-shot corpus measures nothing.

### Design: one stream, two arms

- Ingest a date-ordered stream twice from the same save checkpoint:
  **Arm OFF** (never dream) vs **Arm ON** (dream fires deterministically every k docs).
- Everything else frozen. Snapshot both arms at 25/50/75/100% of the stream — bloat and
  precision drift are *slopes*; two arms can match at doc 50 and diverge at doc 500.

### Seeded ground truth (~20–30 injected cases per stream)

- **Must-merge duplicates**: same entity as "BNP Paribas" / "BNPP" / "BNP".
- **Must-NOT-merge traps**: "BNP Paribas" vs "BNP Paribas Fortis" — a false merge silently
  corrupts every future answer about both entities; no accuracy metric shows why.
- **Supersessions**: doc t1 "X is CEO" → doc t5 "Y replaced X" — you know exactly which
  fact should end up archived.

Seeds give pass-level scores: merge precision/recall, forget precision/recall.

### Three probe sets (both arms, every checkpoint)

1. **Current-fact probes** (answers changed mid-stream) — where Dream should WIN by
   removing the stale competitor from retrieval.
2. **Historical probes** ("who was CEO before Y?") — archive-never-delete: if ON loses
   these, the forget pass violates the contract.
3. **Frozen retention probes** (facts Dream had no business touching) — **ON must equal
   OFF exactly**; any regression is the faulty-consolidation failure, not a tradeoff.

### Dream metrics

Update-accuracy lift (ON − OFF) per checkpoint · retention delta (must be 0) ·
boundedness curve (nodes/edges/storage per doc — OFF grows forever, ON should bend) ·
retrieval precision@k over time (the early-warning metric: bloat degrades context before
answers drop) · seeded pass scores · dream cycle token cost · **rollback rate** (a
mechanism rolling back half its passes is unreliable even when surviving passes are good).

### The math: additive, not multiplicative

Dream does NOT double the matrix: static axes have no ON arms; the OFF arm on D5 *is* the
axis-4 run (already paid for); ON exists only where a mechanism exists (today: Graphiti)
and only in the product config. Today that is **+1 ON replay per stream ≈ +3 runs total**.
Later: +1 run per (method-with-mechanism, stream). Checkpoint probing adds ~4× a small
(40–60-question) probe set per run — hundreds of cheap queries, not an explosion.

Sweepable later: dream **frequency** (every 10 vs 50 docs) — too often burns tokens
re-checking a clean graph, too rare lets precision rot; the right cadence is a result,
not an assumption.

**Method-agnostic by design**: same streams, seeds, probes, metrics for every method once
it has its own evolution mechanism (per the contract) — "Graphiti's dream lift vs
LightRAG's dream lift on identical streams" is the legitimate cross-method comparison.

---

## 8. Cost model and estimates

Assumptions: ~800-token episodes/chunks; extractor **gpt-5.4-mini** ($0.75/M in, $0.075
cached, $4.50/M out); blurbs + generation gpt-5.4-mini (nano/local cut these further);
embeddings 3-large ($0.13/M). Treat every number as **±2× until its pilot** (§0 rule 2).
UltraDomain is plain text — the vision PDF parser is bypassed (paste-text/episode path),
parsing cost 0.

### Per-component (per 1M corpus tokens)

| Component | Mechanics | Cost |
|---|---|---|
| Graphiti extraction | ~6–8 LLM calls/episode (extract → resolve → edges → contradictions → summaries) ⇒ ~20× corpus tokens through the extractor; prompt caching (−90% on shared prefixes) absorbs part of it | **$25–40** |
| Contextual blurbs | 1 call per chunk (chunk + doc context) | $4–5 (mini) · ~$1.5 (nano) |
| Embeddings | corpus + node/edge texts | ~$0.15 |
| Contextual RAG alone, total | blurbs + embeddings | ~$5 |
| NaiveRAG alone, total | embeddings only | ~$0.25 |
| Wall-clock (Graphiti) | 10–20 s/episode, resolution slows as graph densifies | ~4–7 h/1M tokens |

(For reference: a full-size gpt-5.4 extractor would run ~$90–130/1M corpus tokens — the
reason the extractor tier is pilot-tested rather than assumed.) The NaiveRAG→Graphiti
indexing gap is ~2–3 orders of magnitude — itself a headline axis-6 result; log the real
numbers.

### Worked example: UltraDomain on Graphiti+Contextual

Corpus sizes (LightRAG paper): Agriculture 2.02M · CS 2.31M · **Legal 5.08M** · Mix 0.62M
= **~10M tokens**.

| | Full (10M tok) | **Capped: 400k/subset (1.6M)** |
|---|---|---|
| Graphiti extraction (5.4-mini) | ~$250–400 | **~$40–65** |
| Blurbs | ~$45 | ~$7 |
| Embeddings | ~$1.50 | ~$0.25 |
| 400 gold Qs, full pipeline + judge | ~$10 | ~$10 |
| **Total** | **~$300–460** | **~$55–85** |
| Wall-clock | ~35–70 h | ~6–11 h |

**Cap rules**: 400k tokens/subset keeps domain diversity and supports 100 gold questions
each at ~15% of the cost; cap Legal hardest; sample **whole documents** to budget, never
truncate mid-document (the graph needs coherent docs).

### Other corpora (capped, Graphiti+base builds, 5.4-mini extractor)

| Corpus | Budget size | Graph build est. |
|---|---|---|
| D1 reduced pools (gold + distractor passages for ~150 sampled Qs per set) | ~400k/set | ~$10–16 each — smaller haystack than the full pool: fine if identical across methods, and documented |
| D5 MultiHop-RAG (609 news articles) | ~0.8–1.2M | ~$25–50 |
| D4 QASPER (~40 papers) | ~300k | ~$8–12 |
| D3 FinanceBench | filings are 50–150k tokens EACH — 50-question slice over ~10–15 filings ≈ 1.5M | ~$40–60 → **pilot first, or defer** |
| D6 LongMemEval | ~115k-token history per question | **deferred to corporate budget** |

### Query-side

~$0.02/question through the full pipeline with 5.4-mini (contextualize→retrieve→grade→
answer→verify); Gemini Flash judge ~$0.002. 150 Qs × 5 configs × 4 datasets ≈ 3,000
answers ≈ **$60–80 including judging** — or ~$20 with the nano arm, **~$5 with the local
Qwen arm** (judge only). Closed-book control: ~$5 (batchable → ~$2.50). Judging and gold-
question generation go through the **Batch API (−50%)**.

### Phase totals on the personal key

| Stage | Spend (API generator) | (local generator arm) |
|---|---|---|
| Harness smoke (20 Qs, tiny corpus) | < $5 | ~$0 |
| Closed-book + base-alone, all datasets | ~$15–25 | ~$5 |
| **Minimum credible bench** (UltraDomain CS+Mix capped, D1-reduced MuSiQue, D5; hybrid + alone + controls; queries + judging) | **~$90–150** | **~$60–110** |
| Full Phase A (adds Agriculture+Legal capped, QASPER, dream ON arm on D5 + seeded stream) | **~$250–400** | **~$180–300** |
| Phase B (LightRAG/HippoRAG/GraphRAG/NaiveRAG on the frozen suite; GraphRAG indexing rivals Graphiti's) | several $100s — **push to corporate budget** | — |

Indexing dominates either way — the local arm saves queries, not builds; its bigger value
is free harness iteration before any paid run.

---

## 9. Execution order (budget-gated: cheap → expensive, go/no-go before each paid tier)

### 9-bis. THE PLAN AS OF 2026-07-06: Mac rehearsal → company PC for real (one-way door)

The full bench runs **free on the company's llmaas models**; the Mac phase is a small-data
rehearsal (~$5–10). Constraints that shape everything:

- **One-way door**: code can enter the company PC but never leave → EVERYTHING must be
  finished and validated on the Mac first: the harness AND all method adapters (NaiveRAG,
  LightRAG, HippoRAG, GraphRAG — dep conflicts resolved with internet available), each
  proven on the small corpus.
- **The suitcase**: repo + offline wheels (`pip download` targeting the company's
  Windows/Python — wheels are platform-specific) + dataset jsonl files (HF is blocked) +
  `.env.company` template. Nothing may need the internet on the other side.
- **No Docker on the PC, but a "machine de dev" exists.** Backend options, in order:
  (1) run the whole backend on the machine de dev if Linux — bundled `falkor_local` just
  works there, PC is only the browser; (2) FalkorDB hosted on the dev machine +
  `GRAPH_BACKEND=falkor_server`; (3) Neo4j Windows zip (Java, no Docker, no admin) +
  `GRAPH_BACKEND=neo4j`. Find out what the dev machine permits BEFORE transfer day.
- **The cheap report** (Mac deliverable): one page per method — concept, design bet,
  rehearsal-grade small-corpus numbers (labeled as such), measured cost/latency, and an
  empty "company-scale result" column the real runs fill in.
- Mac and company numbers NEVER share a table (different models = different bench); the
  extractor spot-check is repeated on llmaas; judge at company = a second llmaas model if
  the catalog has one, else gold-anchored single-family.

**UltraDomain (CS, Legal, Math, Mix) is the first arena** — everything else follows it.

1. **A0 — harness, ~free**: UltraDomain loader (unique-context extraction + 400k/subset
   whole-document capping), result schema (one JSON per (method, dream, dataset) under
   `tests/results/`, config-hashed, generated table), scorers (EM/F1, gold-anchored judge,
   recall@k). Iterate with the local model for $0.
2. **A1 — gold questions + controls, ~$25**: generate ~100 gold Qs/subset from the sampled
   docs (Batch API) + manual verification pass; then closed-book + base-alone on all four
   subsets. Sanity: base beats closed-book. First real table.
3. **A2 — first pilot, ~$5–10**: 100k tokens of UltraDomain-CS into the hybrid; dashboard
   before/after; extrapolate. Includes the **extractor quality spot-check** (20 pages
   gpt-5.4-mini vs gpt-5.4: node/edge counts + eyeball — sparser graph ⇒ upgrade extractor
   and redo the math). **GATE: recompute §8 with real numbers; proceed only if within
   budget.**
4. **A3 — the UltraDomain bench, ~$100–150** (~$70 local arm): build capped CS+Math+Legal+
   Mix hybrid indexes (~$55–85); run 5 configs (closed-book, base-alone, Graphiti-alone,
   hybrid; indexes shared) on ~400 gold Qs ≈ 2,000 answers + judging (~$50). *This alone
   already answers "does the graph pay for itself on top of contextual RAG" across four
   domains.*
5. **A4 — dream axis, ~$5–10**: seeded synthetic stream (~30 docs) to prove the two-arm
   harness; the D5 date-ordered ON replay lands with A5.
6. **A5 — widen, ~$120–200**: D1-reduced MuSiQue, D5 MultiHop-RAG (+ dream ON replay +
   checkpoint probes), QASPER; FinanceBench slice only if its pilot gate passes. Later,
   same-source extensions: UltraDomain `fin` + `politics` subsets.
7. **B — external methods** on the frozen suite (corporate budget preferred): NaiveRAG
   (≈free) → LightRAG → HippoRAG → GraphRAG (most expensive last); then their evolution
   mechanisms per the contract + dream lifts on the same streams.

Protocol rules throughout: frozen samples/order/models/prompts committed before run 1 ·
100–200 Qs per dataset per config, bootstrap 95% CIs, paired per-question comparisons ·
judge against gold, position-swapped, temp 0 · dream arms are paired replays from one save.

---

## Sources

- LightRAG + UltraDomain (corpora, eval protocol, sizes):
  <https://arxiv.org/abs/2410.05779> · <https://aclanthology.org/2025.findings-emnlp.568.pdf> ·
  stats table via <https://arxiv.org/pdf/2508.10391> (LeanRAG, same corpora)
- Judge bias context (verbosity/position): <https://arxiv.org/pdf/2501.03468> (MTRAG)
- LongMemEval (5 abilities incl. knowledge updates + abstention):
  <https://arxiv.org/abs/2410.10813>
- MultiHop-RAG (news, inference/comparison/temporal/null):
  <https://arxiv.org/abs/2401.15391>
- FinanceBench: <https://www.emergentmind.com/topics/financebench> · ConvFinQA/T²-RAGBench:
  <https://www.emergentmind.com/topics/t-2-ragbench> · FinRAGBench-V:
  <https://arxiv.org/abs/2505.17471>
- QASPER (5,049 Qs / 1,585 NLP papers, gold evidence): Dasigi et al., via
  <https://docs.ragas.io/en/v0.3.4/howtos/applications/gemini_benchmarking/>
- Stale-fact rate of plain RAG (15–40%): <https://arxiv.org/html/2606.26511> ·
  temporal-RAG landscape: <https://arxiv.org/abs/2510.13590> ·
  <https://www.emergentmind.com/topics/temporal-retrieval-augmented-generation-rag>
- HippoRAG-standard multi-hop subsets: the HippoRAG papers ·
  <https://arxiv.org/pdf/2603.28886>
- Pricing (verified 2026-07-06): OpenAI
  <https://developers.openai.com/api/docs/pricing> (gpt-5.4 family, caching −90%,
  batch −50%) · gpt-4.1-mini deprecation 2026-11-04 + $0.40/$1.60:
  <https://developers.openai.com/api/docs/models/gpt-4.1-mini> · cross-provider
  comparisons: <https://pricepertoken.com/> · <https://www.aipricing.guru/> ·
  <https://www.morphllm.com/llm-api>
- Local models on Apple Silicon (Qwen 3.5 9B / Gemma 4 12B on 16GB, Qwen 3.6-35B-A3B on
  32GB; Ollama/MLX-LM): <https://insiderllm.com/guides/best-local-llms-mac-2026/> ·
  <https://apxml.com/posts/best-local-llm-apple-silicon-mac> ·
  <https://www.morphllm.com/best-ollama-models>

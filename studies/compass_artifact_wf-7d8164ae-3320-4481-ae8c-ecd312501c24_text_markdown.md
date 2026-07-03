# Evolutive / Self-Maintaining Memory for LLM Agents & RAG: A 2025–2026 SOTA Survey for Building "Noema" on Graphiti + Anthropic Contextual Retrieval

## TL;DR
- **Your conceptual model is well-validated by the 2025–2026 literature** — every pillar (contradiction reconciliation, temporal validity, dedup/entity-resolution, consolidation, value-based forgetting, and a safe-change meta-layer) maps to a named, active research problem — but the single most important finding is a warning: **unchecked, fire-after-every-interaction LLM self-consolidation demonstrably degrades memory below the no-memory baseline** (Zhang et al., "Useful Memories Become Faulty," arXiv 2605.12978; GPT-5.4 failed 54% of ARC-AGI problems it had previously solved, after consolidating from ground-truth). Your "eval-gated, reversible, append-only source-of-truth" meta-layer is therefore not optional polish — it is the exact mitigation the field now prescribes.
- **On the Graphiti substrate, evolution is only partially native**: Graphiti automatically does entity resolution, edge invalidation (invalidate-don't-delete), bi-temporal tracking, and incremental extraction on insert — but it does **NOT** automatically forget/prune/decay, does **NOT** continuously rebuild communities (label-propagation drift requires scheduled `build_communities()` rebuilds), and does **NOT** retroactively re-resolve or merge old entities. Consolidation, pruning, and value-based forgetting must be **built by you** as background workers on top of Graphiti's delete/invalidate APIs.
- **Recommended architecture**: keep raw episodes append-only as first-class evidence (Graphiti episodes = your source-of-truth log); do lightweight resolution/invalidation synchronously on-insert (Graphiti default); run heavier consolidation, community rebuild, and value-based pruning as **async, threshold-triggered, sleep-time background jobs that are eval-gated and reversible**; and treat the Anthropic Contextual Retrieval base as a separately-versioned index that is re-contextualized incrementally when source documents change.

---

## Key Findings

1. **The field has converged on a specific set of named open problems** that evolutive memory addresses: memory bloat/unbounded growth, retrieval degradation at scale, temporal/outdated-fact reasoning, knowledge conflict/contradiction, entity fragmentation, catastrophic interference, and context rot ("lost-in-the-middle"). Most proposed fixes are tested only on LoCoMo/LongMemEval, which are themselves under heavy methodological criticism.

2. **The strongest, newest, and most decision-relevant result is negative**: continuous LLM self-consolidation is fragile. The safe default the literature now prescribes is to retain raw episodes and consolidate sparingly and explicitly — precisely your "safe change" meta-layer.

3. **Graphiti gives you bi-temporal contradiction handling and entity resolution for free on insert, but forgetting, pruning, retroactive re-resolution, and continuous community maintenance are not native** and must be scheduled/built.

4. **Frontier labs mostly ship file/document-style memory + context management, not automatic graph consolidation.** Anthropic (memory tool + context editing), OpenAI (saved memories + chat history), Letta (sleep-time compute / "dreaming"), Google (Titans, a research architecture, not a shipped memory product). No major lab has publicly shipped an automatic background "dreaming" graph-consolidation feature as a product as of mid-2026; "sleep-time compute" is the closest and comes from Letta, not a frontier lab's consumer product.

5. **Benchmarks are non-comparable and contested.** LoCoMo (10 conversations), LongMemEval (500 questions), and BEAM (up to 10M tokens) each measure different things; Letta's plain filesystem agent scored 74.0% on LoCoMo with GPT-4o mini — above Mem0's reported 68.5% for its top graph variant — a warning that benchmark wins may not reflect real memory quality.

---

## Details

### 1. Current problems the field identifies (that evolutive memory fixes)

**Memory bloat / unbounded growth.** Widely documented. Ablations in the "Human-Inspired Memory Architecture" paper (arXiv 2605.08538) show deduplication-based consolidation drove a 58% store reduction with 97.2% retention precision on a VSCode benchmark; the SCM paper (arXiv 2604.20943) shows that removing a working-memory limit causes unbounded growth and retains 35/50 noise concepts. *Status: fixes tested on self-constructed benchmarks.*

**Retrieval degradation as memory grows.** The precision-aware benchmark paper (arXiv 2605.11325) argues LoCoMo/LongMemEval "are structurally unable to distinguish a memory system that retrieves one correct belief from one that retrieves the entire store," and that at thousands of beliefs "full-corpus retrieval becomes architecturally impossible." *Status: problem well-argued; the benchmark is new and self-reported.*

**Temporal reasoning failures / outdated facts.** This is the core motivation for bi-temporal graphs (Zep/Graphiti) and for Mem0g's timestamp handling. Mem0 reports OpenAI memory scored poorly on temporal questions because it "consistently failed to attach timestamps." *Status: tested; vendor self-reported.*

**Contradiction and knowledge conflict.** A mature sub-field. Xu et al.'s "Knowledge Conflicts for LLMs: A Survey" taxonomizes context-memory, inter-context, and intra-memory conflicts. Benchmarks include ConflictBank, WikiContradict, and MAGIC (arXiv 2507.21544, multi-hop inter-context conflicts). Astute RAG (arXiv 2410.07176) found ~19.2% of real web-retrieval instances exhibit knowledge conflicts with ~70% retrieval imprecision. Methods: FaithfulRAG, TruthfulRAG (arXiv 2511.10375), Madam-RAG multi-agent debate (arXiv 2504.13079). *Status: actively tested.*

**Entity fragmentation/duplication.** Addressed by entity resolution in Graphiti, Mem0g's Conflict Detector/Update Resolver, and HippoRAG's synonym detection. *Status: tested.*

**Catastrophic forgetting vs. interference.** SLEEPGATE (arXiv 2603.14517) frames "proactive interference" as a fundamental working-memory bottleneck beyond context length and reports 97–99.5% retrieval accuracy at PI depths 2–10 vs <18% for baselines. *Status: preliminary experiments, self-reported.*

**Context rot / lost-in-the-middle.** Liu et al., "Lost in the Middle: How Language Models Use Long Contexts" (TACL vol. 12, 2024, pp. 157–173) established the U-shaped positional curve: accuracy drops 30+ percentage points when the relevant document sits in positions 5–15 of a 20-document context versus the first or last positions. Chroma Research's "Context Rot: How Increasing Input Tokens Impacts LLM Performance" (Hong, Troynikov, Huber, July 2025) evaluated 18 LLMs "including the state-of-the-art GPT-4.1, Claude 4, Gemini 2.5, and Qwen3 models," concluding "models do not use their context uniformly; instead, their performance grows increasingly unreliable as input length grows" — and, strikingly, that models "perform better on shuffled haystacks than on logically structured ones." Root cause is architectural (RoPE long-term decay + softmax attention dilution). This is the primary reason a retrieved, curated memory beats dumping everything into a long context. *Status: robustly replicated.*

**The faulty-consolidation finding (most important).** Zhang et al., "Useful Memories Become Faulty When Continuously Updated by LLMs" (arXiv 2605.12978, project page dylanzsz.github.io/faulty-memory): "As consolidation proceeds, memory utility first rises, then degrades, and can fall below the no-memory baseline." GPT-5.4 failed 54% of ARC-AGI problems it had previously solved, after consolidating from ground-truth solutions. WebShop dropped from 0.64 at 8 examples to 0.20 at 128 (the no-memory baseline). Their prescription: "treat raw episodes as first-class evidence and gate consolidation explicitly rather than firing it after every interaction," and "always include an episodic-only baseline." The related SSGM governance framework (arXiv 2603.11768) proposes consistency verification, temporal decay, and access control before any consolidation. *Status: strong controlled study; directly validates your meta-layer design.*

### 2. Key papers and systems (2024–2026)

- **A-MEM (Agentic Memory, Zettelkasten)** — Xu et al., arXiv 2502.12110, NeurIPS 2025; GitHub agiresearch/A-mem. Atomic "notes" with contextual descriptions, keywords, tags, embeddings; LLM-driven link generation; **memory evolution** updates old notes' attributes when new memories arrive. Evaluated on LoCoMo/DialSim. *Independent reproductions exist in comparison papers (e.g., MemRefine arXiv 2606.13177).*
- **Mem0 / Mem0g** — arXiv 2504.19413, ECAI 2025. Extract-consolidate-retrieve; Mem0g adds a directed labeled graph with a Conflict Detector + LLM Update Resolver (add/merge/invalidate/skip). Self-reported LoCoMo: 66.9% vs OpenAI 52.9% (26% relative), ~91% lower p95 latency, ~90% fewer tokens. **New (April 2026) algorithm** claims LoCoMo 92.5, LongMemEval 94.4, BEAM 1M/10M 64.1/48.6 at <7,000 tokens/call — but this is now an **ADD-only** pipeline (stores new facts alongside old, does not overwrite). Notably, Mem0 **removed** its graph module in the v3 OSS rewrite (PR #4805, Apr 2026), though the hosted platform keeps graph memory + time-decay. *Vendor self-reported; some independent replications in third-party papers.*
- **MemGPT / Letta + sleep-time compute** — MemGPT arXiv 2310.08560. Letta separates a primary agent from a **sleep-time agent** that edits core memory asynchronously ("dreaming"); Context Repositories add git-based versioning/rollback of memory. Critically, Letta's "Benchmarking AI Agent Memory: Is a Filesystem All You Need?" (Aug 2025) reports: "This simple agent achieves 74.0% on LoCoMo with GPT-4o mini and minimal prompt tuning, significantly above Mem0's reported 68.5% score for their top-performing graph variant" — a strong argument that specialized memory systems add less than claimed. *First-party, but self-selected benchmark.*
- **Zep / Graphiti** — arXiv 2501.13956. See §5.
- **HippoRAG / HippoRAG 2** — arXiv 2405.14831 (NeurIPS 2024) and 2502.14802 ("From RAG to Memory," ICML 2025); GitHub OSU-NLP-Group/HippoRAG. Neurobiological (hippocampal indexing); OpenIE triples + Personalized PageRank over phrase/passage nodes; HippoRAG 2 adds dense-sparse fusion and recognition-memory filtering; ~7 F1-point gain on associative tasks over embedding retrievers. Supports non-parametric continual learning (add passages in O(log N)) but has **no bi-temporal model or forgetting**. *Peer-reviewed.*
- **MemOS / MemoryOS** — Two distinct systems. MemOS (arXiv 2505.22101 short; 2507.03724 full; MemTensor) treats memory as an OS resource via "MemCube" (parametric + activation + plaintext), claims 159% temporal-reasoning improvement + 38.97% overall over OpenAI global memory on LoCoMo, 60.95% token reduction. MemoryOS (arXiv 2506.06326, BAI-LAB, EMNLP 2025 Oral) is a short/mid/long-term hierarchical persona memory with automated user-profile updating. *Vendor self-reported.*
- **Titans** — Behrouz et al. (Google), arXiv 2501.00663, NeurIPS 2025. Neural long-term memory that memorizes at test time via a "surprise" (gradient) metric with a decay/forgetting mechanism; scales beyond 2M tokens. This is a **model-architecture** approach, not a retrieval memory system, and is **not a shipped Gemini feature**. The follow-up MIRAS framework unifies test-time memorization. *Peer-reviewed research, not a product.*
- **Generative Agents** — Park et al., UIST 2023, arXiv 2304.03442. Memory stream scored by recency (exponential decay) + importance (LLM 1–10 rating) + relevance (cosine), plus periodic **reflection** synthesizing higher-level insights. Foundational for value-based retrieval and consolidation.
- **MemoryBank** — Zhong et al., arXiv 2305.10250. Ebbinghaus forgetting curve: memories decay unless reinforced; salience-threshold pruning. Conceptually foundational for your value-based forgetting, but independent tests report weak LoCoMo scores (5–9 points).
- **Cognee** — GitHub topoteretes/cognee; arXiv 2505.24478. ECL (Extract-Cognify-Load) pipeline builds a KG; **`memify` explicitly does self-maintenance**: prunes stale nodes, reweights edges by usage, adds derived facts. Ontology grounding (OWL/RDF + `ontology_valid` flag) and dlt structured ingestion. Incremental: only new/updated files reprocessed on re-run.
- **2026 consolidation/forgetting papers** — SCM (sleep-consolidated memory + algorithmic forgetting, arXiv 2604.20943), SLEEPGATE (arXiv 2603.14517), SSGM governance (arXiv 2603.11768), MemForest (hierarchical temporal indexing, arXiv 2605.23986), Eywa (provenance-grounded, arXiv 2605.30771), plus surveys arXiv 2505.00675 and arXiv 2605.06716.

### 3. What frontier labs actually do

- **Anthropic** — Ships the **memory tool** (`memory_20250818`, GA on Messages API; file-based, client-side storage: create/read/update/delete in `/memories`) + **context editing** (`clear_tool_uses_20250919`, beta `context-management-2025-06-27`; clears stale tool results at a token threshold) + **server-side compaction**. Per Anthropic's "Managing context on the Claude Developer Platform": "combining the memory tool with context editing improved performance by 39% over baseline. Context editing alone delivered a 29% improvement. In a 100-turn web search evaluation, context editing enabled agents to complete workflows that would otherwise fail due to context exhaustion—while reducing token consumption by 84%." Memory is deliberately **file/agent-directed and visible** (explicit tool calls), not an automatic background graph. Separately, **Contextual Retrieval** (Sept 2024) is a *retrieval* technique, not a memory product. No public "Dreams"/background consolidation product. *First-party.*
- **OpenAI** — ChatGPT has **"saved memories"** (explicit, persistent, model-managed updates/merges) + **"reference chat history"** (April 2025; insights from past chats that "change over time"). OpenAI explicitly acknowledged the old system "became stale" and memories "could contradict one another" (their example: "training for a marathon" vs "sprained my ankle") — the new system auto-updates. Implementation of chat-history synthesis is undocumented; third-party reverse-engineering (embracethered.com) shows a "Model Set Context" block. No confirmed background "dreaming." *First-party for features; third-party for internals.*
- **Google/DeepMind** — Titans (arXiv 2501.00663) is research. Gemini personalization exists as a product but no detailed public memory-consolidation architecture. Google's stated position elsewhere favors long context; Titans suggests a hybrid direction. *Mixed.*
- **Letta** — Not a frontier lab, but the clearest "evolutive memory" product: sleep-time compute / "dreaming," memory blocks, git-versioned Context Repositories, `/doctor` memory audits. *First-party.*
- **DeepSeek, Meta, Mistral, xAI** — No first-party persistent/evolving-memory architecture surfaced in this research beyond long-context/sparse-attention work; DeepSeek-V3.1 appears as an *extraction LLM* in third-party Graphiti evaluations, not as a memory system. *Treat as: no public evolutive-memory product found.*

### 4. Benchmarks for long-term/evolving memory

- **LoCoMo** (arXiv 2402.17753, ACL 2024): 10 multi-session conversations, ~1,540 non-adversarial QA (single-hop, multi-hop, temporal, open-domain) + adversarial. Human F1 ~87.9. **Criticisms**: only 10 conversations; adversarial category often excluded; Letta's filesystem agent scored 74.0%, and precision-aware critics (arXiv 2605.11325) note it can't measure retrieval precision.
- **LongMemEval** (arXiv 2410.10813): 500 questions (LongMemEval_S, ~40 sessions, ~115k tokens avg); five abilities — info extraction, multi-session reasoning, **knowledge updates**, temporal reasoning, abstention. Reports a ~30% accuracy drop for commercial assistants. Adds knowledge-update + abstention that LoCoMo lacks.
- **BEAM** (ICLR 2026, "Beyond a Million Tokens"): 100 conversations up to 10M tokens, 2,000 probing questions; tests memory at scale that context windows can't absorb.
- **Non-comparability**: different judge protocols (LLM-as-judge vs binary), different write-path models, small per-category sizes (LongMemEval has ~30 preference questions). By 2026 the field treats long-context benchmarks (NIAH, RULER, BABILong) as measuring a *different* problem (attention over fixed input) than memory (multi-session write-and-retrieve). **Almost all benchmarks grade retrieval, not the write/forget decision** — the exact thing evolutive memory must get right.

### 5. SOTA mechanisms for automatic evolution on Graphiti specifically

**What Graphiti does automatically on insert** (`add_episode`): LLM entity + edge extraction → **entity resolution/dedup** (hybrid: deterministic MinHash+LSH fast path + LLM fallback; embedding + BM25 + graph-traversal candidate search) → **edge dedup + contradiction detection** → **bi-temporal invalidation** (sets `invalid_at` when a fact is superseded, `expired_at` for logical deletion; edges stay in graph) → **entity summary updates** ("entities evolve over time with updated summaries"). Four timestamps per edge: `created_at`, `valid_at`, `invalid_at`, `expired_at`. Incremental, no batch recompute.

**What Graphiti does NOT do automatically (must be built):**
- **Forgetting/pruning/decay** — none. Only invalidate-don't-delete. A `delete_episode` (cascade) and `delete_entity_edge` API exist (with known dangling-reference gaps, issue #1489), but there is no TTL, decay, or value-based pruning. GitHub issue #864 ("How to forget knowledge?") confirms no built-in solution.
- **Continuous community maintenance** — `build_communities()` uses the Leiden algorithm and **rebuilds from scratch** (removes existing communities). Incremental `update_communities=True` on `add_episode` uses label-propagation-style assignment, but the Zep paper concedes communities "gradually diverge… therefore periodic community refreshes remain necessary." So community maintenance = your scheduled job.
- **Retroactive re-resolution/merge** — resolution runs at insertion time only; no automatic retroactive pass merges entities that were split earlier. Resolution quality degrades as entity vocabularies grow.
- **Entity/edge type limits** — hosted Zep caps at 10 custom entity + 10 custom edge types; OSS has no hard numeric cap but practical LLM-classification degradation appears around ~60 types (issue #1211, which forced a user to split into multiple subgraphs and lose cross-graph relationships).

**Zep/Graphiti benchmark numbers (all self-reported by Zep, arXiv 2501.13956):** DMR 94.8% (gpt-4-turbo) vs MemGPT 93.4% — but the paper concedes this is "marginal" and the full-conversation baseline itself hit 94.4%; DMR is a weak benchmark (60 messages/conversation, single-turn recall). LongMemEval: improvements up to 18.5% (15.2% with gpt-4o-mini, 18.5% with gpt-4o) vs full-context baseline, with ~90% latency reduction and ~1.6k tokens/response vs ~115k. Largest category gains in multi-session, preference, and temporal reasoning. Zep's own site cites LoCoMo 94.7% at 155ms and LongMemEval 90.2% at 162ms. **Trust: vendor self-reported; the paper is unusually candid about DMR's weaknesses.** Independent evaluation (arXiv 2606.15903, FORGETEVAL) notes Graphiti's KG abstraction "sheds surface forms" (synthesizes edge facts rather than preserving raw text), which hurts on adversarial substring-recall tests but is by design; that study also confirms Graphiti "exposes neither a per-query purge… nor a release primitive."

**Recommended continuous-maintenance patterns on Graphiti:**
1. Run Graphiti in an **isolated process/microservice** (FastAPI wrapper) — direct in-process integration causes asyncio event-loop crashes ("Future attached to a different loop"), a documented production hurdle.
2. Keep **episodes as your append-only source-of-truth log** (they already are provenance-tracked); never delete episodes as part of consolidation.
3. Do **synchronous on-insert** only what Graphiti already does cheaply (extraction, resolution, invalidation).
4. Schedule **async background jobs** for: periodic `build_communities()` rebuild (label-propagation drift); value-based pruning of stale/invalidated edges; retroactive entity-merge passes; summary refresh. Gate each behind evals + make reversible.
5. Watch **LLM cost**: a single episode fires many LLM calls (extraction + dedup + edge resolution + summary). At scale, batch and cap.

**Graphiti ↔ vector/contextual base consistency:** Graphiti has its own hybrid retrieval (semantic + BM25 + graph + RRF/cross-encoder/graph-distance rerank). Run the Contextual Retrieval vector base and Graphiti as two retrieval sources fused at query time, with episodes as the shared provenance key linking a chunk to the graph facts it produced.

### 6. How Anthropic Contextual Retrieval fits with an evolving graph

Contextual Retrieval = contextual embeddings + contextual BM25 + rerank. Per Anthropic's Sept 2024 "Contextual Retrieval in AI Systems" post, the technique cuts the top-20-chunk retrieval failure rate 35% with Contextual Embeddings alone (5.7%→3.7%), 49% with Contextual Embeddings + Contextual BM25 (5.7%→2.9%), and 67% when reranking is added (5.7%→1.9%): "This method can reduce the number of failed retrievals by 49% and, when combined with reranking, by 67%." Anthropic's cookbook recommends retrieving the top-20 chunks, weighting dense embeddings ~0.8 vs sparse BM25 ~0.2 (0.25), and using a small Haiku-class model with **prompt caching** to contextualize each chunk cheaply. **Keeping it in sync as the corpus evolves:**
- Contextual chunks are generated by prepending an LLM-written context string to each chunk before embedding/indexing. When a **source document changes**, you must **re-contextualize the affected chunks** (the context string references neighbor/document state) and re-embed + re-index them — incremental reindexing, not full rebuild.
- Use **prompt caching** on the document during contextualization to keep cost down (Anthropic's cookbook pattern).
- Treat the contextual base as **versioned/immutable per document version**; on update, write new chunk versions and retire old ones, mirroring Graphiti's invalidate-don't-delete so the two layers stay temporally consistent.
- Link each chunk to the Graphiti **episode** it was ingested as, so graph facts and chunks share provenance and can be invalidated together.

### 7. Automatic vs on-insert vs scheduled maintenance — the design space

| When | What to run | Trade-off |
|---|---|---|
| **Synchronous on-insert** | Extraction, entity resolution, edge invalidation (Graphiti default) | Immediate consistency; adds ingestion latency + LLM cost; risky if consolidation is heavy |
| **Async background workers** | Consolidation, summary refresh, dedup passes | Keeps write path fast; needs a queue + isolation; eventual consistency (Mem0 users report correct answers appearing "hours later after background graph processing") |
| **Sleep-time / idle consolidation** | Reflection, community rebuild, value-based forgetting | Letta's model; uses idle compute; matches human consolidation; but this is exactly where the faulty-memory risk lives |
| **Threshold-triggered** | Prune when store > N; rebuild communities when drift > threshold | Bounds growth; needs good triggers |

**Making continuous self-maintenance safe (directly tied to the faulty-memory finding):**
- **Append-only episodic source of truth** — raw episodes are first-class evidence; consolidation is a derived, disposable layer.
- **Eval gates** — before committing a consolidation, run it against a held-out eval (LongMemEval-style + your domain set) and an **episodic-only baseline**; if the consolidated memory can't beat raw retrieval, discard it (Zhang et al.'s explicit recommendation).
- **Reversibility/rollback** — Graphiti's `expired_at` + episode provenance let you reconstruct prior state; Letta's git-versioned Context Repositories are the reference pattern.
- **Consolidate sparingly** — not after every interaction; the safest schedule in the faulty-memory study was infrequent/"Static-Group."

**Per-substrate view (how much evolution is native vs must be built):**

| Capability | Graphiti (now) | HippoRAG/HippoRAG 2 | LightRAG | Cognee |
|---|---|---|---|---|
| Incremental ingestion | Native | Native (O(log N)) | Native (incremental) | Native (only new/changed files) |
| Entity resolution/dedup | Native (on insert) | Synonym detection | Entity/relation dedup | Native |
| Temporal / bi-temporal | **Native (bi-temporal)** | None | None | Versioning + temporal edges |
| Contradiction/invalidation | **Native** | None | None | Invalidate-don't-delete |
| Communities | Semi (manual/scheduled rebuild) | N/A (PPR) | Native (dual-level) | Native |
| Forgetting/pruning/decay | **Must build** | Must build | Must build | **Native (`memify`)** |
| Consolidation/reflection | Must build | Must build | Must build | Partial (`memify` derived facts) |
| Retroactive re-resolution | Must build | Must build | Must build | Partial |

Graphiti is the strongest substrate for **temporal + contradiction** out of the box (your temporal-validity and reconciliation pillars are native). Cognee is the only one with **native self-maintenance/forgetting** (`memify`) — worth studying as a reference for what you'll build on Graphiti. HippoRAG 2 is the strongest for **associative multi-hop retrieval** but is not temporal and does no forgetting — a "later" retrieval-quality upgrade, not an evolution engine.

---

## Recommendations

**Stage 1 — Foundation (now).** Adopt Graphiti as the bi-temporal substrate in an isolated microservice. Keep episodes append-only as source-of-truth. Use only on-insert resolution/invalidation. Stand up the Anthropic Contextual Retrieval base as a separately-versioned index linked to episodes by provenance key. Fuse the two at query time. *Benchmark to move on: ingestion latency and per-episode LLM cost acceptable at your volume.*

**Stage 2 — Safe background evolution.** Add async workers for (a) scheduled `build_communities()` rebuilds, (b) value-based pruning of stale/invalidated edges, (c) summary refresh, (d) incremental re-contextualization of changed chunks. **Gate every consolidation behind an eval harness that includes an episodic-only baseline; auto-rollback if it doesn't beat baseline.** *Threshold to trigger pruning: store size or retrieval-precision degradation; threshold to rebuild communities: measured label-propagation drift.*

**Stage 3 — Value-based forgetting & consolidation.** Implement a Generative-Agents-style recency+importance+relevance score and a MemoryBank-style decay/reinforcement, but consolidate **sparingly** (idle/sleep-time, not per-interaction). Add contradiction-resolution policies (temporal precedence via Graphiti's valid-time; multi-source debate for non-temporal conflicts). *Change your approach if: consolidated memory underperforms raw episodic retrieval on your eval — then reduce consolidation frequency toward zero.*

**Stage 4 — Retrieval-quality upgrades (later).** Evaluate adding HippoRAG 2-style Personalized PageRank over the entity graph for associative multi-hop, layered on top of Graphiti — as a retrieval enhancement, not a replacement for the temporal engine.

**Governance throughout.** Adopt the SSGM-style ordering: consistency verification + temporal decay + access control *before* any memory commit. Version everything (Letta Context-Repository pattern). Log every automatic mutation with provenance and a reversible diff.

---

## Caveats
- **Benchmark numbers are mostly vendor self-reported and non-comparable** (Mem0, Zep, MemOS all report wins on differently-configured LoCoMo/LongMemEval runs). Treat all single-system headline numbers as directional, not settled. The Letta filesystem result (74.0% LoCoMo with no memory system) is a sober reminder.
- **The faulty-memory finding (arXiv 2605.12978) is recent and may not yet be independently reproduced at scale**, but it aligns with the broader interference literature (SLEEPGATE, SSGM) and is the most important design input for you.
- **Graphiti's "does NOT do automatically" list is based on current docs, code index (DeepWiki), the Zep paper, and GitHub issues (#864, #1211, #1489)** — Graphiti is evolving fast (v0.21+ added batch dedup; sagas added summarization), so re-verify the forgetting/community APIs at build time.
- **Several 2026 arXiv IDs cited here (e.g., 2605.*, 2606.*) are very recent preprints** surfaced in this research; verify peer-review status before relying on their specific numbers.
- **Frontier-lab internals (OpenAI chat-history synthesis, any background consolidation) are undocumented**; claims about "no dreaming feature" reflect absence of public evidence, not confirmed absence.
- Some numbers here (Anthropic 84%/39%, Chroma 18-model context-rot study, Contextual Retrieval 49%/67%) come from vendor blogs/first-party posts, not peer-reviewed venues.
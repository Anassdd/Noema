# Evolutive Memory — A Readable Guide
*What it is, what it fixes, how the frontier does it, and how to build it on Graphiti. Plain-language and examples first; the heavy science is at the very end.*

---

## The one-paragraph version

An **evolutive memory** is a memory that cleans up after itself. As your chatbot reads more documents and has more conversations, a naive memory just piles everything up — and gets slower *and dumber*. An evolutive memory instead keeps fixing itself: it settles contradictions, tracks what's true *now* vs. what *was* true, merges duplicates, summarizes clutter into cleaner knowledge, and forgets junk. The catch the whole field has learned in 2026: if you let an LLM rewrite its own memory unchecked, it often makes it **worse** — so every self-edit has to be checked and reversible. That safety rule is the heart of doing this well.

---

## Part 1 — The 6 jobs of an evolutive memory (with examples)

Think of these as six things a healthy memory does *to itself*. Each has a problem it fixes and a concrete example.

### 1. Reconciliation — settle contradictions
**Problem:** two documents disagree, and the memory holds both, so answers flip-flop.
**Example:** A 2023 report says *"the fund's target allocation is 60% equities."* A 2025 report says *"40% equities."* Without reconciliation, ask "what's the target?" and you get whichever chunk happened to surface. With it, the memory knows the 2025 one supersedes the 2023 one.

### 2. Temporal validity — track *when* things were true
**Problem:** old facts get served as if current.
**Example:** *"The CFO is Lars."* was true in 2022. In 2026 that's wrong. A temporal memory stamps each fact with a lifespan ("valid 2022→2024"), so it can answer both *"who is CFO now?"* (current) and *"who was CFO in 2023?"* (history) — without deleting anything.

### 3. Deduplication — one real thing = one entry
**Problem:** the same entity gets stored under several names, splitting its knowledge into fragments.
**Example:** *"BNP Paribas,"* *"BNPP,"* and *"BNP Paribas SA"* become three separate nodes. A question that should connect facts about the bank fails because the facts are scattered across three half-pictures. Dedup merges them into one — and suddenly multi-hop reasoning works.

### 4. Consolidation — turn scattered facts into cleaner knowledge
**Problem:** the memory only holds tiny isolated facts, never the big picture.
**Example:** Across 30 documents the memory has "rates rose in Q1," "rose in Q2," "rose in Q3." Consolidation produces the higher-level fact "rates rose steadily through 2025" — so it can answer a big-picture question no single document stated.

### 5. Forgetting — drop what no longer earns its place
**Problem:** noise and dead weight bury the good answers (and yes, bloat).
**Example:** A one-off detail from a document nobody's queried in a year keeps showing up as a near-match, crowding out the relevant result. Forgetting scores each item (how recent, how often used, how important, how connected) and prunes the low-value ones so the *right* answer stops competing with junk. This also fights **interference** — many *near-identical* entries corrupting recall of the right one, a distinct problem from raw bloat.

### 6. Safe change — never trust a self-edit blindly *(the meta-rule)*
**Problem:** automatic self-maintenance can *introduce* errors — merging things it shouldn't, forgetting things it needed.
**Example:** The memory "helpfully" merges *"Apple (the company)"* and *"apple (the fruit)"* because they share a name — corrupting both. Safe change prevents this with two rules: keep an untouchable raw record you can always rebuild from, and treat every maintenance pass as a *proposal* that must prove it improved things before it's kept (and can be rolled back if not).

**How they group:**
- **1–2** keep memory *correct and current*
- **3–4** keep it *connected and synthesized*
- **5** keeps it *sharp and lean*
- **6** makes doing all of it *automatically* actually safe

---

## Part 2 — Why this matters more than "the graph got big"

The instinct is that evolution is about keeping the graph small and fast. That's real but secondary. The bigger truth from the 2026 research:

**A bloated memory doesn't just get slow — it gets *wrong*.** More entries mean more near-duplicate and stale candidates competing at retrieval time, so the correct answer gets buried. Cleaning improves *accuracy*, not just speed. This is the single most important reframe: evolutive memory is mainly a **correctness** mechanism.

And the sharpest finding of all (see the science section): letting an LLM continuously rewrite its own memory *unchecked* can drag performance **below having no memory at all**. That's why "automatic" must always mean "automatic **and** gated **and** reversible."

---

## Part 3 — What the big labs actually do (2025–2026)

Short version: **the frontier is moving toward external, self-managing memory — but nobody has fully "solved" automatic evolution, and the ones who ship it keep it gated.**

- **Anthropic** — ships a **memory tool** (Claude reads/writes memory files that persist across sessions) plus **context editing** (auto-clears stale tool calls to keep the working window clean). Reported big gains from combining them. Also authored **Contextual Retrieval** (your base layer). Direction validates your whole approach: external memory + active pruning beats stuffing everything in context.
- **OpenAI** — ChatGPT has **saved memories** + **reference chat history**, and in **June 2026 shipped "Dreaming" (V3)**: a **background process that automatically synthesizes and self-updates memory** — e.g. it revises *"going to Singapore in July"* into *"went to Singapore in July 2026"* once the trip passes — now the standalone memory foundation, replacing the manual saved-list. OpenAI reports factual-recall success climbing 41.5% → 67.9% → **82.8%** across its 2024 → 2025 → 2026 systems. This is the clearest **production** proof of automatic background consolidation — **and it walks straight into the faulty-consolidation risk** (an LLM continuously rewriting its own memory). That is exactly why job 6 (eval-gate + reversibility) is what separates a Dreaming that helps from one that quietly rots.
- **Google / DeepMind** — pushing **long context** (huge windows) as a partial substitute, plus research (Titans) on models that *learn what to remember at test time*. Their own production guidance still routes factual/private questions through retrieval, not pure long-context.
- **Letta (ex-MemGPT)** — the "memory OS" idea: the agent manages its own memory with tools, plus **sleep-time compute** (consolidate while idle). Closest public thing to your background-worker design.
- **Others (DeepSeek, Meta, Mistral, xAI)** — more focused on efficient long-context/attention than on evolving structured memory.

The honest pattern: labs converge on **background consolidation + external memory + keep-it-gated**. That's exactly the design you're aiming at.

---

## Part 4 — How to build automatic evolution on **Graphiti** (your current target)

The key insight: **Graphiti gives you some of the six jobs for free; the rest you build on top.** Don't rebuild what it already does.

**What Graphiti does natively (jobs 1, 2, 3 — mostly free):**
- **Temporal validity (job 2)** — it's bi-temporal by design: every fact carries valid-time + ingestion-time, and it *invalidates-don't-delete* (marks old facts superseded, keeps history). This is exactly your Kendra-shoes / CFO example, built in.
- **Reconciliation (job 1)** — when a new fact contradicts an existing edge, it invalidates the old one automatically on insert.
- **Deduplication (job 3)** — entity resolution runs *on insert* (matches a new mention to an existing node).

**What you must build on top (jobs 4, 5, 6 — not native):**
- **Forgetting / pruning (job 5)** — Graphiti doesn't drop low-value nodes on its own. You add a scheduled pass that scores items (recency × frequency × importance × connectedness) and prunes.
- **Consolidation (job 4)** — merging many small facts into semantic summaries is yours to build (and community rebuilding needs periodic refresh).
- **Safe change (job 6)** — the eval gate + reversibility is your architecture, not Graphiti's.
- **Retroactive re-resolution** — Graphiti resolves entities as they arrive; catching duplicates that only become obvious *later* is an extra background pass you add.

**The recommended shape (automatic but safe):**
1. **On insert (synchronous, fast):** let Graphiti do its native thing — extract, resolve, invalidate. Users wait only for this, and it's light.
2. **Background worker (async, idle/threshold-triggered):** run the built-on-top jobs — consolidation, pruning, retroactive dedup, community refresh.
3. **Eval gate before committing:** each background pass produces a *candidate*; keep it only if it beats current memory on a small eval set; else roll back.
4. **Append-only episodic log underneath:** the raw facts are never mutated, so any bad pass is fully recoverable.

**When to run it (the timing question):**
- Cheap, safe operations (native resolution/invalidation) → **on insert**.
- Expensive, risky operations (consolidation, pruning) → **background, scheduled or idle**, never blocking the user, always gated.

---

## Part 5 — Keeping the Contextual Retrieval base in sync as memory evolves

Your base layer (Anthropic Contextual Retrieval) and the Graphiti graph are **two lenses on the same chunks**, so when memory changes, both must stay consistent:

- **New document arrives** → chunk it → generate the contextual blurb → add to the vector + BM25 base **and** feed episodes to Graphiti. Both lenses updated from the same source.
- **A fact gets invalidated in the graph** → the underlying chunk usually *stays* in the vector base (it's still true history), but retrieval should prefer current facts. The graph's temporal layer is what carries "current vs. old," not the vector base.
- **Re-contextualizing:** if a document's meaning shifts because of new context, its chunks *can* be re-blurbed and re-embedded — but that's expensive, so do it in the background, gated, not on every change.

The clean rule: **the graph owns "what's true now"; the vector base owns "find me relevant text." Keep them fed from the same chunks, and let the graph's temporal layer handle currency.**

---

## Part 6 — Per-substrate view (how much evolution is native)

| Job | Graphiti | HippoRAG (later) | LightRAG (later) | Cognee (reference) |
|---|---|---|---|---|
| 1 Reconciliation | native | build it | partial | invalidate-don't-delete |
| 2 Temporal validity | native (bi-temporal) | build it | build it | versioning + temporal edges |
| 3 Deduplication | native (on insert) | build it | partial | native |
| 4 Consolidation | build it | build it | build it | partial (memify derived facts) |
| 5 Forgetting | build it | build it | build it | **native (memify)** |
| 6 Safe change (gate) | your architecture | your architecture | your architecture | your architecture |

**Takeaway:** Graphiti is the *evolution-friendliest* substrate — it hands you jobs 1–3. HippoRAG gives stronger multi-hop *retrieval* but you build almost all the evolution around it. This is exactly why you test Graphiti first for the evolving-memory story, and HippoRAG later for the retrieval-quality story. **Cognee** is the outlier worth studying: it's the only substrate with **native forgetting** — `memify` prunes stale nodes, reweights edges by usage signals, and adds derived facts with *no full rebuild* — so it's the working **template** for the pruning/consolidation worker you'll build on Graphiti.

---
---

# The Science (heavier detail, sources, trust levels)

*Read this only when you want the receipts. Trust legend:* **(A)** first-party/peer-reviewed · **(B)** reputable preprint/eng blog · **(C)** vendor self-reported / unreproduced. *Evidence:* [TESTED] reproduced · [SELF-REPORTED] · [PROPOSED] architectural only.

## Open problems the field names
- **Unbounded growth / memory bloat** — memory grows without limit; retrieval degrades. Widely documented. **(B)**
- **Retrieval degradation with scale** — accuracy (not just latency) drops as memory grows; the correct item is buried among near-duplicates. **(B)**
- **Temporal reasoning failure / stale facts** — models serve outdated facts; poor at "as of when." Motivates bi-temporal graphs. **(A/B)**
- **Knowledge conflict / contradiction** — coexisting contradictory facts; retrieval is order/luck-dependent. **(B)**
- **Entity fragmentation** — same entity under multiple nodes; breaks multi-hop. **(B)**
- **Context rot / lost-in-the-middle** — long-context models miss mid-context info; long context is not a memory substitute. **(A/B) [TESTED]**
- **Proactive interference** — many *similar* stored items crowd out the right one and corrupt recall — a bottleneck distinct from raw store size or context length (SLEEPGATE). Forgetting/pruning fights this, not just bloat. **(B) [SELF-REPORTED]**
- **Faulty self-consolidation (the critical one)** — unchecked LLM self-consolidation degrades memory *below the no-memory baseline*. This is the empirical basis for eval-gated, reversible maintenance. **(B) [TESTED]** — verify the specific 2026 preprint before citing a number.

## Key systems & papers (2024–2026)
- **Zep / Graphiti** — bi-temporal knowledge-graph memory; episodes → entity/edge extraction, valid-time + ingestion-time, invalidate-don't-delete, on-insert entity resolution. Reports strong LongMemEval / DMR numbers. **(B/C) [SELF-REPORTED]** — the temporal mechanism is real and inspectable; the leaderboard numbers are vendor-reported.
- **A-MEM** — agentic "Zettelkasten" memory; notes link and evolve over time. **(B) [PROPOSED/partially tested]**
- **Mem0 / Mem0g** — extract-and-consolidate memory, plus a graph variant; popular, self-reported LoCoMo gains. **(C) [SELF-REPORTED]**
- **MemGPT / Letta** — memory-OS; agent manages memory via tools; **sleep-time compute** for idle consolidation. Filesystem-agent results notable but see benchmark caveat. **(B)**
- **HippoRAG / HippoRAG 2** — neurobiological; Personalized PageRank over an entity graph; strong multi-hop, cheap indexing. Peer-reviewed. **(A) [TESTED]** Not natively incremental.
- **MemOS / MemoryOS** — "memory operating system" framing; scheduling/versioning of memory. **(B/C)**
- **Titans** — learns what to memorize at test time; recall beyond 2M tokens. Peer-reviewed core; independent reimplementation found gains softer than headline. **(A/B) [TESTED, mixed]**
- **Cognee** — the reference for **native self-maintenance**: its `memify` post-processing prunes stale nodes, reweights edges by usage signals, strengthens frequent connections, and adds derived facts, writing back to graph + vector + metastore with **no full rebuild**. The closest shipped analog to the forgetting/consolidation worker you'll build on Graphiti. **(B) [vendor-documented]**
- **Memary, MemoryBank (Ebbinghaus forgetting), Generative Agents (memory stream)** — additional forgetting/consolidation designs; mostly **(B/C) [PROPOSED]**.

## Benchmarks (and their caveats)
- **LoCoMo** — long conversational memory; widely used but criticized for non-comparable setups across papers. **(B)**
- **LongMemEval** — targets long-term memory abilities (temporal reasoning, knowledge updates, multi-session); the more respected of the two. **(B)**
- **BEAM** and other 2026 entrants — newer, watch for adoption.
- **General caveat:** almost all agent-memory leaderboard numbers are **[SELF-REPORTED]**; setups differ; treat cross-system comparisons skeptically. A filesystem-agent baseline reportedly hit ~74.0% on a memory benchmark, a caution that simple baselines can rival elaborate memory systems.

## Frontier-lab specifics (first-party where marked)
- **Anthropic (A):** memory tool + context editing in the Developer Platform; reported +39% agentic-search improvement combining them and large token savings; Contextual Retrieval (−49%/−67% retrieval-failure reductions). First-party.
- **OpenAI (A):** ChatGPT saved memories + chat-history reference; **"Dreaming" (V3) shipped June 4 2026** — a background process that automatically synthesizes and self-updates memory, now the standalone foundation replacing the manual saved-memories list. Reported factual-recall task success 41.5% (2024) → 67.9% (2025 + Dreaming V0) → **82.8% (Dreaming V3)**. First-party announcement; internal mechanism undisclosed. *Confirmed via web search, July 2026 — this supersedes the compass artifact's "no confirmed dreaming" caveat.*
- **Google/DeepMind (A/B):** Titans research; Gemini long-context; production guidance favors retrieval+grounding for factual/private data.
- **Letta (B):** sleep-time compute; memory-management tool patterns.

## Graphiti mechanism detail (for the build)
- **Native:** episode ingestion → LLM entity/edge extraction → **on-insert entity resolution** → **temporal edge invalidation** (valid-time + ingestion-time; superseded edges marked, not deleted) → optional community detection.
- **Not native (build it):** value-based **forgetting/pruning**; **semantic consolidation** of many facts; **retroactive** re-resolution of duplicates discovered later; scheduled **community rebuilds**; the **eval-gate + rollback** safety layer.
- **Sync pattern with Contextual Retrieval:** feed the same chunks to both; graph carries currency (temporal), vector base carries relevance; re-contextualize/re-embed only in gated background passes.

## Maintenance timing — the design space
- **On-insert (sync):** cheap, safe ops (native resolution/invalidation). User-visible latency, so keep light.
- **Async background worker:** expensive ops (consolidation, pruning, retro-dedup). Never blocks the user.
- **Sleep-time / idle-triggered:** run when the system is quiet (Letta pattern).
- **Threshold-triggered:** after N new episodes.
- **Safety (non-negotiable):** append-only episodic log as source of truth + eval-gated, reversible passes — directly answers the faulty-self-consolidation finding.

## Honest status line
The **six-job conceptual model is well-supported** by the literature. The **mechanisms** are a mix of tested (HippoRAG multi-hop, context-rot, Anthropic Contextual Retrieval, the degradation finding) and proposed-but-not-independently-reproduced (most memory-product leaderboard numbers). **Adopt patterns, not vendor benchmarks**, and validate on your own corpus with your bench.

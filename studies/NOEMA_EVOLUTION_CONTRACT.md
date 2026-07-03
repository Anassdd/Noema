# Noema — The Evolution Contract
*The fixed goal, invariants, interface, and measuring-stick that EVERY memory type's
auto-evolution must respect — so Graphiti, LightRAG, HippoRAG, Cognee, and Naive/Contextual
RAG all pursue the **same goal** and stay **comparable**.*

Sources: `compass_artifact_…_markdown.md` (evolution SOTA survey) + `NOEMA_EVOLUTIVE_MEMORY_READABLE.md`
(plain-language guide) + `NOEMA_MEMORY_SOTA.md` §4.

## How to read this
Evolution mechanisms **differ per substrate and that is fine** — it's the thing under study.
What must NOT differ is the **contract**: the problems targeted, the safety invariants, the
operation interface, and the eval harness. Build each engine against Parts B–C, measure it
against Part D, and use the Part E backlog to know what that specific substrate must build.

> One-line rule: **standardize the goal, the safety, the interface, and the scorecard — vary
> only the mechanism.**

---

## Part A — The Problems to Fix (the fixed target set)

Every method's evolution must move these needles. If a method optimizes something else, the
comparison is meaningless. Six "jobs" (content) + one meta-rule; job 5 carries four measurable
sub-axes that a plain "forgetting" label hides.

| # | Job (fix) | Problem it kills | Measured by |
|---|---|---|---|
| 1 | **Reconciliation** | contradictory facts coexist; answers flip by luck-of-retrieval | contradiction-handling score |
| 2 | **Temporal validity** | stale facts served as current; no "as-of" | temporal / as-of accuracy |
| 3 | **Deduplication / resolution** | one entity split across nodes → multi-hop breaks | duplicate-entity rate; multi-hop recall |
| 4 | **Consolidation / synthesis** | only scattered atoms; can't answer "the overall theme" | global/thematic QA score |
| 5 | **Forgetting / pruning** | four distinct failures below | four sub-axes ↓ |
| 5a | ↳ bounded growth | store grows forever → slow + costly | node/edge/chunk count vs budget |
| 5b | ↳ retrieval precision at scale | big store buries the right item in near-dupes | precision@k as store grows |
| 5c | ↳ interference resistance | many *similar* items crowd each other out (≠ volume) | recall under proactive-interference depth |
| 5d | ↳ context-rot avoidance | curated memory beats dumping into long context (attention dilution) | answer accuracy vs dump-everything baseline |
| 6 | **Safe change** *(meta)* | unchecked self-edit degrades memory *below no-memory baseline* | must clear the Part D gate |

Note 5b (retrieval noise from store size) ≠ 5d (attention dilution in the prompt): related
conclusion ("keep it small and curated"), **different cause, different metric** — keep them apart
when measuring even though one mechanism (forgetting) helps both.

---

## Part B — The Base Concept: invariants EVERY substrate must respect

These are non-negotiable regardless of mechanism. They are the empirical mitigation for the
field's sharpest finding (unchecked LLM self-consolidation drops below the no-memory baseline —
Zhang et al.).

- **I1 · Append-only source of truth.** Raw episodes/chunks are first-class evidence, never
  mutated or deleted. All evolution is a **derived, disposable, rebuildable** layer on top.
- **I2 · Invalidate / demote — never destroy.** Forgetting removes an item from *active
  retrieval*, keeping the evidence + history for audit and "as-of" queries. (bitemporal
  `invalid_at`/`expired_at` where native; an `archived` flag where not.)
- **I3 · Eval-gated commits with a mandatory episodic-only baseline.** No consolidation / prune /
  merge is committed unless it **beats raw episodic retrieval** on a held-out eval. Otherwise
  auto-rollback. This is the teeth of I1–I2, not optional polish.
- **I4 · Reversibility + provenance.** Every automatic mutation is a versioned, reversible diff,
  traceable to its source episode. (Letta Context-Repository / git-versioned pattern.)
- **I5 · Sparingly + non-blocking.** Heavy evolution runs async / idle / threshold-triggered,
  **never per-interaction, never on the user's write path**, always gated. Cheap ops only
  (native resolution/invalidation) run synchronously on insert.
- **I6 · Protected set.** User beliefs, hub/high-centrality nodes, facts cited in a saved answer,
  and anything inside the audit-retention window are **never auto-pruned**.
- **I7 · Governance before commit (SSGM order).** consistency-check → temporal-decay →
  access-control → *then* write. Log every mutation.

---

## Part C — The Shared Interface (so mechanisms are swappable + comparable)

Fix these four so one policy/scorer reads all substrates; only the *execution* of each verb is
method-specific.

- **Operation verbs:** `ADD · MERGE · UPDATE · INVALIDATE · SKIP` (Mem0g). The **decision of
  which verb** is a shared reconciliation step (identical prompt/policy across methods); only the
  *apply* is native.
- **Memory-item schema:** `id · content · provenance(→episode) · validity(valid_at, invalid_at) ·
  value_score`. Every substrate exposes this shape even when a field is trivial (Naive RAG's
  `valid_at` may be null) — that's what lets one scorer grade all of them.
- **Value / forgetting score:** `recency-decay + importance + relevance + provenance-depth +
  centrality` (Generative-Agents + MemoryBank, enriched for graphs). Used to **demote only**,
  never to delete. Shared across methods; honors I6.
- **Trigger contract:** `on-insert (cheap only) · async-background · idle/sleep-time ·
  threshold-triggered`, with the **same thresholds** so cost and staleness are measured on equal
  footing.

---

## Part D — The Measuring Stick (so "same goal" is verifiable)

Almost all benchmarks grade *retrieval*, not the *write/forget decision* — the exact thing
evolution must get right. So the harness must:

- **Grade the write/forget decision:** use **LongMemEval** (has *knowledge-updates* + *abstention*
  categories LoCoMo lacks) + a temporal/contradiction set + your domain set.
- **Always run the episodic-only baseline** alongside (I3's teeth). If evolution can't beat "just
  keep the raw log," it's off.
- **Same scorecard per method:** update-correctness · contradiction-handling · as-of accuracy ·
  boundedness (5a) · precision-at-scale (5b) · interference (5c) · context-rot (5d) ·
  staleness-window · non-destruction/recoverability · **incremental cost (tokens + LLM calls)**.
- **Three passes** (holds the confound-free comparison from the design notes):
  - **C-pass (control):** all methods get dumb re-ingest → isolates *retrieval* under change.
  - **B-pass (ablation):** each method evolution ON vs OFF → compare the **lift**, not the
    absolute (normalizes away the different mechanisms — this is the fair cross-method number).
  - **A-pass (realistic):** each method at its native best → the product-relevant result.

---

## Part E — Per-Substrate Build Backlog (mechanism varies; contract does not)

Native = free; **build** = you implement it to satisfy Parts A–C. This is the per-method to-do.

| Job | Graphiti | LightRAG | HippoRAG 2 | Cognee *(reference)* | Naive / Contextual |
|---|---|---|---|---|---|
| 1 Reconciliation | **native** (on-insert invalidation) | partial | build | invalidate-don't-delete | build (version-retire) |
| 2 Temporal validity | **native** (bi-temporal) | build | build | versioning + temporal edges | build |
| 3 Deduplication | **native** (on-insert) | partial | synonym detection | native | re-embed/merge |
| 4 Consolidation | build (+ scheduled `build_communities()`) | native dual-level | build | partial (`memify` derived facts) | build |
| 5 Forgetting | build (value-based prune) | build | build | **native (`memify`)** | build |
| 6 Safe change | your architecture (I1–I7) | your architecture | your architecture | your architecture | your architecture |
| — Retroactive re-resolution | build | build | build | partial | n/a |

Reading it: **Graphiti** hands you jobs 1–3 free → best "evolving-memory" substrate → build first.
**Cognee** is the only one with native forgetting (`memify`) → **study it as the template for the
prune/reweight/derive worker you build on Graphiti.** **HippoRAG 2** is the strongest *multi-hop
retrieval* engine but you build nearly all evolution around it → a later *retrieval-quality*
story, not an evolution engine. **LightRAG** gives dual-level communities (job 4) but you build
temporal + contradiction.

⚠ Re-verify Graphiti's forgetting/community APIs at build time — v0.21+ added batch dedup and
sagas added summarization, so the "build" column is shrinking. Run Graphiti in an isolated
process (asyncio event-loop isolation) — direct in-process integration crashes.

---

## Part F — Workflow per method

1. Take the Part E column for the substrate.
2. Implement its **build** cells so it satisfies **Part A** (the jobs), obeying **Part B** (I1–I7)
   and exposing **Part C** (verbs + item schema + score + triggers).
3. Run it through the **Part D** harness (C/B/A passes, episodic-only baseline always on).
4. Keep only what beats baseline (I3). Record the scorecard row.
5. Repeat for the next substrate. Same contract → the rows are comparable → "which is best for
   what, and how much does its evolution buy it" becomes a real answer.

**The honest guardrail:** a filesystem agent scored ~74% on LoCoMo — above elaborate graph memory
systems. The episodic-only baseline (I3 + Part D) is your defense against building an impressive
evolution engine that loses to just keeping the raw log.

# Noema — Production Architecture & Handover Study

*2026-07-16 · a study, not a change: nothing in the repo moves until each stage below is
explicitly approved. Companion to the frozen design docs in this folder.*

## 0. The question

The system works end-to-end and is heading for handover to people who did not build it.
What is the best production-level organization, and how do we make the codebase trivially
transferable **without losing a single piece of information** — code, data, decisions, or
the reasons behind them?

The study concludes: **the architecture is already sound; the production gaps are almost
all about *where state lives* and *what is written down*, not about the code's shape.**
The highest-value plan is four small, staged interventions — and a deliberate refusal to
do the big cosmetic reshuffle that would *feel* like productionization while destroying
the very things that make this repo transferable (a coherent docs book, per-module
histories, and decision records that reference real paths).

---

## 1. Current state, measured

~8.2k lines of backend Python, small and legible. Layering is real today:

| layer | where | LOC | state |
|---|---|---|---|
| HTTP surface | `app/routers/` (11 thin routers) | 1,150 | good — no business logic |
| Expert loop | `app/pipeline.py` | 590 | good — one file tells the whole answer story |
| Memory engines | `app/retrieval/`, `app/graph/`, `app/lightrag/`, `app/textgraph/` (dormant) | 2,685 | good internals, **implicit common interface** |
| Ingestion | `app/parsing/`, `app/chunking/` | 801 | good |
| Bench | `app/bench/` | 2,395 | good — jobs, resume, honest reports |
| Infra | `config.py`, `llm_client.py`, `saves.py`, `schemas.py`, `main.py` | ~780 | good — the provider seam holds |
| User data | `auth_store.py`, `conversation_store.py`, `beliefs.py`, `memory_*` | ~580 | good code, **bad locations** |

Already production-grade and worth saying out loud in any handover: one provider seam
(OpenAI ↔ llmaas is a `.env` swap, enforced by convention *and* module structure), pinned
requirements with upgrade instructions in the file header, 8 no-network test suites
(54 tests) guarding the load-bearing contracts, resumable/detached long operations with
per-unit persistence, a versioned save/checkpoint system, an honest self-pricing benchmark,
an 11-chapter docs book, and a `studies/` folder that is a genuine decision record.

## 2. The gaps, ranked by (production risk × handover confusion)

### Gap 1 — Runtime state is scattered across the source tree ★ the big one

Where mutable data actually lives today:

| artifact | current location | smell |
|---|---|---|
| conversations DB | `backend/app/conversations.db` | **inside the Python package** |
| user memory | `backend/app/memory.json`, `app/memory.md` | inside the package |
| textgraph store | `backend/app/textgraph_store/` | inside the package |
| vector base | `backend/.chroma/` | hidden dir at backend root |
| datasets | `backend/data/bench/` (+ gitignored `raw/`) | fine, but a third convention |
| FalkorDB persistence | `tests/results/graph_store/` | **production data under `tests/`** |
| bench workdirs (gold, runs, reports) | `tests/results/bench/` | production data under `tests/` |
| induced schemas | `tests/results/graph_schemas/` | same |
| graph saves registry | `tests/results/graph_saved/` | same |
| users/beliefs | `backend/.users`* / `backend/.beliefs` | hidden dirs |

A newcomer cannot answer the two questions that define operability: *"where does my data
live?"* and *"what do I back up / migrate / wipe?"* The `tests/results/` placement is
actively misleading — deleting "test results" would destroy the knowledge graph.

**Fix (Stage 1): one state root.** `NOEMA_STATE_DIR` (default `backend/var/`), with every
module's default derived from it in `config.py` — the only file that knows the layout:

```
backend/var/
├─ chroma/          # vector base            (was backend/.chroma)
├─ falkor/          # graph DB + server      (was tests/results/graph_store)
├─ lightrag/        # LightRAG stores
├─ textgraph/       # dormant engine's store (was app/textgraph_store)
├─ schemas/         # induced domain schemas (was tests/results/graph_schemas)
├─ saves/           # save registry          (was tests/results/graph_saved)
├─ bench/           # workdirs: gold, runs   (was tests/results/bench)
├─ users/           # auth + per-user memory (was app/*, backend/.users)
└─ conversations/   # chat history           (was app/conversations.db)
```

Every location stays individually overridable by the existing env vars (`VECTOR_DIR`,
`GRAPH_DB_DIR`, `BENCH_WORK_DIR`, …) — they just default relative to the root. A
`scripts/migrate_state.py` moves existing data once and verifies counts afterwards.
`tests/results/` keeps only true test artifacts (saved scenario runs, lab fixtures).

**Git policy stays a decision, now written down:** the repo deliberately commits
knowledge stores (the "suitcase" property — the corpus-indexed-multiple-ways travels to
the company machine as files). Keep that, but make it explicit per directory in a
STORAGE.md table (committed / gitignored / migratable), so the next person understands
it's a choice, not an accident.

### Gap 2 — The pluggable-memory promise has no visible seam

CLAUDE.md's core architectural rule — "memory strategies are interchangeable behind ONE
interface" — is true in behavior but **implicit in code**: `pipeline.retrieve` branches on
flags, each engine has its own manager and save shape, and the bench maps configs to flag
tuples. Nothing a newcomer can open and read as *"this is what a memory method IS"*.

**Fix (Stage 2): `app/engines/base.py`** — a `MemoryEngine` protocol with the five verbs
the system already exercises everywhere, plus a registry:

```python
class MemoryEngine(Protocol):
    name: str
    async def ingest(self, doc, *, domain_id) -> IngestReport: ...
    async def query(self, q, *, domain_id, k, doc_id=None) -> list[ScoredChunk]: ...
    async def inspect(self, *, domain_id) -> EngineStats: ...      # nodes/chunks/health
    async def save(self, domain_id, name) / restore(...)           # checkpoint seam
```

Adapters wrap the existing engines without moving their internals. `pipeline.retrieve`
and the bench's `CONFIGS` consume the registry. Payoff: LightRAG drops into the bench as
a config (already agreed), Phase-B methods (HippoRAG, NaiveRAG) become "write one
adapter", and the architecture's central promise becomes a 60-line readable file.

### Gap 3 — No packaging, task runner, or CI

There is no `pyproject.toml`, no `make`, no CI. Everything runs, but only via commands
that live in people's heads and doc prose.

**Fix (Stage 4, cheap):**
- `backend/pyproject.toml` (project metadata; deps still driven by the pinned
  `requirements.txt`, which the locked-down install depends on).
- A `Makefile` at the root — the handover interface:
  `make dev` (backend+frontend), `make test` (all 8 suites), `make build`,
  `make migrate-state`, `make smoke` (the free end-to-end checks).
- GitHub Actions: run the 8 no-network suites + `vite build` on every push (<2 min,
  $0 — every suite was designed offline-first, which makes this free).
- A tiny logging setup module (uvicorn access logs are the only server logs today) +
  `/system/version` returning the git SHA, so "what is deployed?" has an answer.

### Gap 4 — Tribal knowledge not yet promoted into the repo

The docs book is strong, but several load-bearing facts live only in commit messages,
code comments, or session lore: the FalkorDriver event-loop binding, "one uvicorn worker
by design" (in-memory jobs registry, index cache, graph manager), `--reload` kills
detached runs, fingerprint/comparability discipline, why hybrid is supplement-fusion
(measured), the free-tier-data rule. Handover fails on exactly these.

**Fix (Stage 0 — docs only, do first):**

| new doc | contents |
|---|---|
| `ARCHITECTURE.md` (root) | the one-pager: 3 mermaid diagrams (query flow, ingest flow, bench flow), the layer table above, the **explicit runtime model** — one uvicorn worker, one FalkorDB process, in-memory job/cache registries, what breaks if you scale horizontally and why that's fine here |
| `STORAGE.md` (root) | the data map: every path × what writes it × lifecycle × committed-or-ignored × how to back up/restore/wipe |
| `RUNBOOK.md` (root) | operate it: start/stop, pause/resume/reattach a bench run, restore a save, rotate a key, the top-8 failures with their fixes (429 storms, judge fallback, build_skip surprises, reload-mid-run) |
| `docs/12-gotchas.md` | the hall of measured lessons: fusion history, event-loop binding, prompt-cache mechanics, fingerprint rules — with links to the studies where each was established |
| `GLOSSARY.md` | domain_id, save, episode, blurb, gold, fingerprint, config, scope, dream, judge rubric… (~25 terms that gate every conversation about this system) |
| `studies/README.md` | an ADR-style index: decision · date · status (frozen/superseded) · doc — turning the folder into a navigable decision record |
| `README.md` (rewrite top) | 5-command quickstart + the **3-day onboarding path** (below) |

### Minor notes (recorded, not urgent)

- `app/` root mixes expert-loop, user-data and infra modules — acceptable at 12 files;
  see §4 for why a re-nesting is *not* recommended now.
- `textgraph/` is dormant by decision — mark `DORMANT` in its docstring and the map,
  don't delete (it's a candidate "instant lens" and costs nothing).
- Script-style tests are unconventional but a *feature* here (zero deps, run offline on
  the locked-down machine); add `tests/run_all.py` so CI and humans share one entry.
- Frontend structure (`api/` per resource, feature folders) is fine; document the
  production serving story (vite build → static host or FastAPI mount) in RUNBOOK.

## 3. Target layout (end state after all stages)

```
noema/
├─ ARCHITECTURE.md  STORAGE.md  RUNBOOK.md  GLOSSARY.md  README.md  RUN_ON_WINDOWS.md
├─ Makefile
├─ backend/
│  ├─ app/                      # code only — no mutable state anywhere below app/
│  │  ├─ config.py  llm_client.py  main.py  schemas.py  logging_setup.py
│  │  ├─ engines/               # base.py (protocol + registry) + adapters
│  │  │   ├─ retrieval/  graph/  lightrag/  textgraph/   (internals unmoved)
│  │  ├─ pipeline.py  beliefs.py  memory_judge.py  memory_store.py
│  │  ├─ ingestion → parsing/  chunking/                 (names unchanged)
│  │  ├─ bench/
│  │  ├─ routers/
│  │  └─ auth_store.py  conversation_store.py  saves.py
│  ├─ var/                      # ALL runtime state (NOEMA_STATE_DIR)
│  ├─ data/bench/               # tracked datasets (+ gitignored raw/)
│  ├─ pyproject.toml  requirements*.txt  .env.example
├─ frontend/
├─ tests/                       # suites + streamlit lab; results/ = test artifacts only
├─ docs/                        # the book, 01–12
└─ studies/                     # decision record + README index
```

Note what did **not** change: package names, module names, router names, the docs book's
references. The tree above is today's tree plus `var/`, `engines/base.py`, packaging
files, and five documents.

## 4. What NOT to do (and why — this is half the study)

1. **No big-bang re-nesting** (`app/core/`, `app/expert/`, `app/api/`…). It reads as
   "production" but: every docs-book chapter, study, commit message and code comment
   references current paths; `git log --follow` survival is partial at best; and the
   information-preservation requirement is exactly what a mass rename endangers. A
   newcomer is served far better by ARCHITECTURE.md mapping the real tree than by a
   prettier tree with broken references. Revisit only if a team adopts the repo
   long-term, and then as one `git mv` commit paired with the full doc update.
2. **No infrastructure upgrades that violate the deployment constraint.** Postgres,
   Redis, Celery, Docker-compose orchestration — the production target is a locked-down
   Windows box with no Docker and no admin. File-backed stores and stdlib auth are not
   prototypes to outgrow; they are the design. Write that down (done: ARCHITECTURE.md).
3. **No pytest migration, no repo split, no microservices.** Single repo = the suitcase.
   One process = the concurrency model every cache and registry assumes, documented
   rather than "fixed".

## 5. Migration plan — staged, each stage shippable, nothing lost

| stage | what | risk | effort | prerequisite |
|---|---|---|---|---|
| **0. Write it down** | the 7 documents of Gap 4 | zero | ~half a day | none — do first |
| **1. One state root** | `var/` + config derivation + `migrate_state.py` + STORAGE.md update | low (paths only; every dir keeps its env override; migration script verifies counts) | ~half a day | 0 |
| **2. Engine protocol** | `engines/base.py` + registry; pipeline + bench consume it; LightRAG becomes a bench config | medium (touches retrieve/CONFIGS — the fusion tests + a new engine-contract test guard it) | ~a day | 1 |
| **3. (deferred) re-nesting** | only on explicit request | high (references) | — | team decision |
| **4. Ops floor** | pyproject, Makefile, CI, logging, /system/version | zero-to-low | ~half a day | none (parallel) |

Information-preservation rules for every stage: each move ships **in the same commit** as
its doc update; `studies/` is append-only (supersede, never edit history); anything
learned during migration goes into `docs/12-gotchas.md`; the migration script never
deletes — it moves and verifies.

## 6. The handover kit (what the next person receives)

1. **README quickstart** — clone → `.env` from example → `make dev` → open two pages.
2. **The 3-day onboarding path:**
   - *Day 1 — run it:* README, ARCHITECTURE.md, GLOSSARY; `make dev`; upload one PDF,
     watch the graph grow, ask one question, click a citation. `make test` (all free).
   - *Day 2 — read it:* docs 04–07 with the code side-by-side (the book was written for
     exactly this); trace one question through `pipeline.py`; open STORAGE.md and find
     every artifact your Day-1 actions created.
   - *Day 3 — trust it:* studies/README index → NOEMA_EVAL_BENCH + BENCH_DATASETS; run
     the cheap basel-faq bench (~$9) end-to-end: estimate gate → build → detached run →
     reattach once on purpose → read the report's CIs and verdict.
3. **RUNBOOK.md** for the operator, **RUN_ON_WINDOWS.md** for the deployer,
   **docs/12-gotchas.md** for the maintainer, **studies/** for whoever asks "why".
4. **CI green badge** — the promise that the 54 contracts hold on every change.

## 7. Recommendation

Execute stages **0 → 1 → 4 → 2** (docs first, state root second, ops floor third, engine
protocol when LightRAG joins the bench — which is already agreed). Defer stage 3
indefinitely. Total effort ≈ 2–3 working days, zero paid tokens, and every step leaves
the repo strictly more transferable than the day before.

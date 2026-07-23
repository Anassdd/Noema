# Changelog

What each push adds, newest first.

## 2026-07-23 — Task-matched reasoning effort + chat effort selector

- Every LLM role now runs at a research-backed thinking depth (quality-first):
  judge **high** (the one role with measured accuracy gains from effort),
  graph extractor **medium** (analysis-class; deeper shows no extraction
  gain), contextualizer **low** (summarization-class), answers **medium**.
  All env-tunable (JUDGE/EXTRACT/CONTEXT/CHAT_REASONING) and dropped
  automatically on non-reasoning models.
- New **Effort selector in the composer** (themed pill next to the retrieval
  selector): Auto / Low / Medium / High per conversation, persisted, applied
  to both plain and expert answers. One entry per push (a push may carry several
commits — they're grouped under its date and headline). Update this file as
part of every push.

## 2026-07-23 — benchdata/ tracks on single-repo deployments

- `benchdata/` is no longer in the tracked .gitignore: at work (one GitLab
  repo, data inside) its files — datasets, workdirs, run results — commit
  like any other, so overnight runs can never be silently skipped. On the
  Mac, where benchdata/ is its own GitHub clone, it's ignored locally via
  .git/info/exclude (one line, documented). Only datasets/raw and inflight
  state stay ignored everywhere. RUN_ON_WINDOWS §7 rewritten for the
  single-repo work setup.

## 2026-07-23 — Bench data split for real: benchdata/ clone-in-place

- All bench data (12 datasets, workdirs, archives, raw sources) now lives ONLY
  in the noema-bench-data repo, cloned INTO the project at `benchdata/` (its
  own gitignored git checkout; a ../noema-bench-data sibling also works).
  Auto-detected — zero configuration on any machine; explicit BENCH_*_DIR env
  vars and NOEMA_STATE_DIR still override.
- `make sync` pulls the code and the data repo together; setup is one command:
  `git clone <data-repo-url> benchdata`.
- Legacy in-repo data locations removed from tracking and fully gitignored.
- RUN_ON_WINDOWS §7 rewritten for the clone-in-place setup (GitLab at work).

## 2026-07-23 — Stage 4 (security) + stage 5 (coding) bench datasets

- **s4-cticonnect** (1,859 expert-curated QA, CC-BY-4.0): cyber-threat
  intelligence over a 6,365-entry corpus (ATT&CK techniques, CWE, CAPEC,
  3,011 CVEs, 321 vendor reports). Nine task slices — entity linking,
  attribution, multi-doc synthesis — the graph stress test. Prose gold is
  judged; the ground-truth ID rides as an alt answer.
- **s5-sweqa-light / -heavy** (480 + 192 curated questions): SWE-QA over 14
  pinned real Python repos, one document per source file. A question enters
  the gold only when its WHOLE repository fits the prepare cap, so corpora
  stay repo-complete. sympy dropped (25MB of symbolic-math source for 48
  questions; GitHub's 100MB file cap decided). No evidence spans released —
  evidence columns stay blank for this stage.
- New adapters: cticonnect.py, sweqa.py.

## 2026-07-22 — Bench data back in-repo (split postponed)

- The datasets and prepared workdirs return to the product repo (legacy
  locations, tracked again) so today's single-zip workflow keeps working —
  now including the four staged additions: s1-crag (1,399 Q, all CRAG
  domains), s1-hotpotqa (7,405 Q), s2-cuad (4,182 Q), s3-finqa (883 Q).
- The separate noema-bench-data repo and the BENCH_*_DIR env seam stay
  available for the planned GitLab split — just unused for now.

## 2026-07-22 — Production mode + sectioned Settings; No-memory default

- **Production mode** (Settings → Application, persisted): hides the token
  metrics — per-answer context/prompt/response breakdown, the session meter and
  the live estimate — for a clean end-user app; the runtime trace and model
  picker stay. Chat window, message list and composer all follow the flag.
- **Settings panel reorganized into sections**: Appearance / Chat / Memory /
  Application / Administration, replacing the flat toggle list.
- **New conversations start in "No memory"** (plain chat): retrieval is
  something the user opts INTO, not out of — the memory selector still offers
  Live memory and every saved snapshot one click away.
- The in-app /settings guide reflects the new panel layout.

## 2026-07-22 — /settings command (app help on demand)

- New `/settings <question>` command: the full app guide (header icons,
  Settings rows, composer selectors, slash commands, memory behavior) is
  loaded for that ONE answer — asked as plain chat, no retrieval — then gone.
  Normal chats carry only a one-line identity that redirects "how do I…?"
  questions to /settings instead of guessing. Replaces the short-lived
  always-in-context guide from earlier today.

## 2026-07-22 — Personal memory v2 + web retrieval mode

- **Personal memory rebuilt as four markdown files per account** (frontier
  synthesis: Claude's self-edited files + ChatGPT's dated facts + Hermes' caps,
  no embeddings anywhere):
  - `profile.md` — topical `## Topic` sections of connected prose; the judge
    *rewrites the section* a new fact belongs to (weave, never append).
  - `now.md` — dated time-bound facts (`fact (learned → until)`); expired facts
    auto-retire to history at session start.
  - `history.md` — retire-don't-delete archive with date ranges; never injected.
  - `journal.md` — one dated line per chat per day (background pass, 30-min
    floor, catch-up batching); deleting a conversation cascades its lines out
    via a provenance sidecar. Oldest entries compact into monthly digests.
- **Compact-note style** ("Interning at BNP Paribas." — no "The user is…"),
  caps as consolidation walls (merge/tighten/retire, never silent loss),
  env-tunable (`MEMORY_PROFILE_CAP` / `MEMORY_NOW_CAP`).
- **Beliefs/notes upgraded**: dated + deduped, reversal-aware (a changed
  opinion *replaces* the old note), shared per domain across saves (legacy
  per-save files merge lazily), consolidation instead of silent truncation.
- **Context assembly**: memory block frozen per conversation (prompt-cache
  safe), authority-ordered tail (archive → notes → sources → question).
- **Archive recall server-side in `/chat`**: IDF-scored history+journal lookup
  on every message — no extra round-trip, no regex gate to miss; LLM query
  expansion fires only on explicitly past-referential lexical misses
  ("the Turkish trip" → istanbul).
- **`?view=memory` page**: standalone app-shell surface — four editable files,
  cap gauges, profile-topic chips, cross-tab theme sync, dark/light toggle,
  refresh/save toasts. Memory events now show as a notification above the
  composer instead of transcript notes.
- UX fixes: send auto-scroll, themed canvas behind overscroll (no white flash).
- Tests: 13-case no-network memory suite + user-run live judge eval
  (`tests/eval_memory_live.py`).
- **Web retrieval mode**: provider-side `web_search` (Responses API — proxy-
  viable), offered as a retrieval mode when the gateway supports it. Model
  defaults: parse → `gpt-5.6-terra`, bench judge → `gpt-5.6-sol`. SQuAD
  general-domain bench adapter.

## 2026-07-21 — Bench campaign hardening + memory evolution v1

- Bench: kill switch + save provenance (creator models per engine); recommended
  models as defaults; answer reuse on judge-only re-runs; run deletion;
  per-dataset running badges; app-theme styling with dark/light toggle.
- Multi-dataset jobs: parallel per-dataset runs with locked concurrency,
  independent tails, isolated stop; overnight campaigns with a pull-proof
  local results archive.
- Automatic memory evolution v1 (ops judge: add/update/delete) + markdown-file
  editing; per-user saves; existence-aware chat selectors; no-memory option.
- French parity + LLM-call economy; refreshed knowledge stores.

## 2026-07-20 — Admin layer

- Account management page, seeded default admin, admin-only bench, protected
  bench content. FinanceBench re-prepared at 100k cap (pilot size).

## 2026-07-17 — Production organization (stages 1 + 4)

- `NOEMA_STATE_DIR` seam consolidating all runtime state (opt-in).
- Ops floor: Makefile, pyproject, one test entry point.

## 2026-07-16 — Bench trust pass + handover docs

- Decoupled parallel judging, judge rubric v2, statistical priced reports
  (bootstrap CIs, McNemar); Graphiti document-tuned extraction with recipe and
  concurrency seams; contextual retrieval excerpt mode + cached BM25.
- Bench runs survive the tab (detached server jobs with reattach); first
  prepares of the human-gold datasets; retired stale datasets.
- Handover documents (architecture study stage 0); CLAUDE.md refreshed.

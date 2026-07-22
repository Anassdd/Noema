# Changelog

What each push adds, newest first. One entry per push (a push may carry several
commits — they're grouped under its date and headline). Update this file as
part of every push.

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

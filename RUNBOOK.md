# RUNBOOK.md — operating Noema day to day

For whoever runs it. Setup lives in [README.md](README.md) (Mac) and
[RUN_ON_WINDOWS.md](RUN_ON_WINDOWS.md) (prod); this page is what you do *after* it runs.

## Start / stop

```bash
make backend        # uvicorn app.main:app --reload  (port 8000)
make frontend       # vite dev server                (port 5173)
make test           # all free suites — run after ANY change, takes ~1 min
```

- FalkorDB (`falkor_local`) auto-starts inside the backend on port 6399 and persists to
  the graph store dir — you never manage it separately on dev.
- **`--reload` restarts on any file edit and kills in-flight bench runs** (they resume at
  zero re-cost, but don't edit code during a long run — or run
  `uvicorn app.main:app` without `--reload` for campaign days).
- Frontend production build: `make build` → `frontend/dist/` (serve with any static
  server; the dev proxy in `vite.config.js` maps `/api` → `:8000`).

## Bench runs (the paid operations)

1. **The estimate gate is the contract** — the Run button shows build + query cost before
   anything is spent. An unpriced-model warning means the number is a floor, not a quote.
2. Runs are **detached jobs**: closing the tab changes nothing; reopening the page
   reattaches and replays the log. **⏸ Pause** stops the server-side job.
3. Everything resumes at its own granularity: build (per episode / per document), answers
   (per question), verdicts (per verdict). Press Run again after any interruption —
   nothing already paid is re-paid.
4. Four consecutive infrastructure errors trip the circuit breaker (an outage must never
   be scored as low accuracy, or burn budget on empty answers). Wait out the outage,
   press Run.
5. **Comparability rules**: a build is reusable only under the same fingerprint
   (corpus · cap · extractor · embeddings · episode version); judge rubric and graph
   search recipe are stamped in each report's provenance. Never put runs with different
   stamps in one table. `rejudge` re-scores an old run under the current rubric for free.

## Saves (checkpoints)

Create/restore from the graph page. A Graphiti save = graph + its vector base together;
a LightRAG save = the whole workspace. Bench builds auto-checkpoint as saves
(`bench-<dataset>-<cap>k-<fp>`). Restore never deletes the live memory; it swaps what
answers.

## Keys & config

- All secrets live in `backend/.env` (gitignored — keep it that way). Rotate = edit +
  restart. `backend/.env.example` documents every variable; deeper: docs/03.
- Provider swap (dev ↔ prod) = `LLM_PROVIDER` + that provider's vars. No code change —
  if a code change seems needed, that's a bug in the provider seam.
- **Changing the chat model?** Resize `CONTEXT_DOC_CAP` (≈20k under the model's usable
  input). Wrong cap = hard API errors mid-ingestion on big documents.
- Free-tier judge? Set `JUDGE_RPM≈9`. Paid judge: leave it unset (full speed,
  `JUDGE_CONCURRENCY` parallel verdicts).

## The top failures and their fixes

| symptom | cause | fix |
|---|---|---|
| run log stops, tab was closed | nothing is wrong — the job kept running | reopen the bench page; it reattaches |
| `run aborted: N questions in a row failed` | provider outage tripped the breaker | wait, press Run — resumes exactly there |
| every hybrid/graph answer errors, vector fine | FalkorDB down or wrong `GRAPH_BACKEND` | check port 6399 (dev) / the Docker container (Windows) |
| `event loop is closed` on graph calls | a second driver/instance was created outside `graph_manager` | always go through `graph_manager.get()`; see docs/12-gotchas |
| 429 storms during a build | provider rate limits vs Graphiti's fan-out | lower `GRAPH_MAX_COROUTINES` (try 8), `CONTEXT_CONCURRENCY=1` |
| blurb calls fail on one huge document | doc over the model's input window | lower `CONTEXT_DOC_CAP` — excerpt mode takes over automatically |
| judge accuracy suddenly shifts between runs | different judge model or rubric version | read `provenance` in both reports — don't compare across stamps |
| "build already exists" but you expected a rebuild | same fingerprint → `build_skip` reused it | change what should differ (cap/extractor) or bump deliberately; never delete the save to force it |
| a "test cleanup" deleted the graph | state lives under `tests/results/` (historical) | restore from git (stores are tracked); adopt `NOEMA_STATE_DIR` (STORAGE.md §3) |
| paid a build twice on two datasets with same corpus | different dataset names = different fingerprints | expected — fingerprints are per prepared corpus |

## Weekly hygiene (5 minutes)

`make test` green · commit tracked stores if the knowledge changed (dedicated refresh
commit) · copy the personal-data dirs somewhere safe (STORAGE.md §2) · glance at
`tests/results/bench/*/runs/inflight/` — a non-empty file means an unfinished run to
resume or clear.

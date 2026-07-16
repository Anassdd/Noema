# STORAGE.md — where every byte of state lives

The operator's data map: every mutable artifact, who writes it, whether git tracks it,
and how to back it up or wipe it. **Read this before deleting anything** — some
production state currently lives in surprising places (yes, under `tests/results/`).

An optional consolidated layout exists behind `NOEMA_STATE_DIR` (see §3) — until you
opt in, the historical locations below are the live ones.

## 1. The data map

| artifact | location (default) | env override | written by | git | lose it and… |
|---|---|---|---|---|---|
| **Vector base** (Chroma: chunks, blurbs, embeddings) | `backend/.chroma/` | `VECTOR_DIR` | ingestion, bench builds | **tracked** (suitcase) | re-ingest every document (paid: blurbs + embeddings) |
| **Knowledge graph** (FalkorDB dump + server files) | `tests/results/graph_store/` | `GRAPH_DB_DIR` | graph ingestion, Dream, bench builds | **tracked** | re-extract every document (the most expensive artifact in the repo) |
| **LightRAG workspaces** | `backend/data/lightrag/` | `LIGHTRAG_DIR` | LightRAG ingestion | ignored | re-ingest for that engine |
| **Induced schemas** (per-domain extraction types) | `tests/results/graph_schemas/` | — | schema induction | tracked | re-induce (one cheap LLM call per domain) |
| **Bench workdirs** (frozen corpora, gold, runs, reports, inflight resume records) | `tests/results/bench/<dataset>/` | `BENCH_WORK_DIR` | prepare, runs, judge | **tracked** (gold + reports are deliverables) | lose gold approvals, run reports, and resume state |
| **Bench datasets** (converted, public) | `backend/data/bench/*.json` | `BENCH_DATA_DIR` | adapters | **tracked** | re-run adapters (raw sources re-downloadable) |
| **Bench raw sources** (CRAG bz2, SEC PDFs, BIS crawl) | `backend/data/bench/raw/` | — | you / adapters `--crawl` | **ignored** | re-download (~740MB; instructions in `studies/BENCH_DATASETS.md`) |
| **Accounts + sessions** (PBKDF2 hashes, opaque tokens) | `backend/data/auth/` | — | auth_store | **ignored** (personal) | everyone re-registers |
| **Per-user chat memory** | `backend/data/memory/<user>.md` | — | /remember, memory judge | ignored | users lose remembered facts |
| **Legacy global memory** (pre-accounts, no longer read by code) | `backend/app/memory.json`, `backend/app/memory.md` | — | nothing (inert) | ignored | nothing — kept only as a pre-accounts artifact |
| **Conversations** (SQLite) | `backend/app/conversations.db` | — | chat | ignored | chat history gone |
| **Beliefs** (per user × memory context) | `backend/.beliefs/` | `BELIEFS_DIR` | ✎ Beliefs panel, /note | ignored | user notes gone |
| **Textgraph store** (dormant engine) | `backend/app/textgraph_store/` | — | dormant | ignored | nothing (engine unused) |
| **Test artifacts** (scenario runs, lab fixtures, stress outputs) | `tests/results/{graph_runs, context_runs, parser_runs, …}` | — | test scripts | tracked | re-run the suites (some cost cents) |

## 2. Policies, spelled out

- **Committed knowledge stores are a decision, not an accident.** The repo is the
  transfer medium to a machine that may have no internet ("the suitcase"): the corpus
  indexed multiple expensive ways travels as files. Refresh them only in dedicated
  `Refresh committed knowledge stores` commits — never folded into feature commits —
  and never commit stores containing non-public documents.
- **Personal data never enters git**: auth, conversations, per-user memory, beliefs are
  all ignored. Verify with `git check-ignore` before changing any of those paths.
- **Backup** = two things: commit the tracked stores (knowledge), copy
  `backend/data/{auth,memory}`, `backend/.beliefs`, `backend/app/conversations.db`
  (people). Nothing else is state.
- **Wipe a domain** = the graph page's reset (graph) + deleting its Chroma collection —
  never by deleting directories while the server runs (FalkorDB and SQLite hold handles).

## 3. The consolidated layout (opt-in)

Set `NOEMA_STATE_DIR` (e.g. `backend/var`) and every default above moves under one root:

```
$NOEMA_STATE_DIR/
├─ chroma/  falkor/  lightrag/  textgraph/     # engine stores
├─ schemas/                                     # induced domain schemas
├─ bench/                                       # workdirs (gold, runs, resume records)
├─ auth/  memory/  conversations/  beliefs/     # people
```

Individual env overrides still win over the root. To adopt it:

```bash
# 1. STOP the backend (open file handles — see §2)
# 2. preview:   python scripts/migrate_state.py --state-dir backend/var
# 3. execute:   python scripts/migrate_state.py --state-dir backend/var --apply
# 4. add NOEMA_STATE_DIR=backend/var to backend/.env, restart, run `make test`
```

The script only moves and verifies — it never deletes, and it refuses to run if the
FalkorDB port answers. Until you run it, nothing changes.

# 11 — Roadmap & known limitations

What is deliberately not built yet, what is known-imperfect, and where the project goes
next. Kept honest on purpose — a successor should trust this list.

## Known limitations (current build)

| Area | Limitation | Status |
|---|---|---|
| Dream / consolidate | Graphiti 0.29.2 `build_communities()` spun at 100 % CPU on FalkorDB → pass disabled by default (`DREAM_COMMUNITIES=1` to enable) | re-test on library upgrades |
| Parsing / docintel | Azure Document Intelligence path is wired and import-verified but **never run against a live DI resource** | validate on the company's Azure before relying on it |
| Graph backend | `falkor_embedded` flaky under concurrent writes | use `falkor_local` (default) or a server |
| Windows | bundled FalkorDB is Unix-only → Docker FalkorDB + `GRAPH_BACKEND=falkor_server` required | documented in RUN_ON_WINDOWS.md |
| Evaluation | no benchmark harness yet — retrieval quality is judged by inspection (lab traces), not measured | the single biggest missing piece, see below |
| Beliefs | single-user (`user="default"` in the file key); multi-user drops in via the same key scheme | fine for the internship scope |
| Testing | backend logic suites exist (parser/chunker/contextual/retrieval/graph); no UI tests, no CI | acceptable now; CI is cheap to add |
| Personal memory | global across chats by design; not per-domain | revisit if it confuses users |

## Next: the evaluation bench (prerequisite for everything else)

The one piece the remaining roadmap blocks on. Goals:

1. **Method comparison** — index the same corpus as naive RAG / contextual RAG / Graphiti
   (later LightRAG, HippoRAG) behind one `retrieve(query) → evidence` interface, ask the
   same question set, score retrieval (recall@k, precision) and answers (EM/F1 or judge),
   plus latency/tokens. Question types matter: single-hop, multi-hop, global/thematic, and
   **temporal** — each method should win somewhere; that's the finding.
2. **The Dream eval gate** — a small temporal probe set (update / as-of / contradiction /
   abstention questions with authored gold answers) + an episodic-only baseline. Any
   evolution pass must score ≥ the pre-pass graph to commit. This turns Dream's sanity
   checks into true quality gates.

Datasets shortlisted: MuSiQue/HotpotQA/2Wiki (multi-hop, published baselines),
FinanceBench/ConvFinQA (banking domain), LoCoMo/LongMemEval + time-sliced corpora (the
temporal/evolution track — evolution is invisible on a static corpus).

## Phase 2 — evolutive memory (beyond the button)

- Automatic Dream triggers: every N episodes / nightly / idle — same passes, same gate.
- Value-scored forgetting: usage (a retrieval hit-counter), recency, connectivity,
  provenance depth → **demotion** tiers, never deletion; protected set (user beliefs,
  hubs, cited facts) untouchable.
- Consolidation re-enabled once the library-level community build is fixed; Cognee's
  `memify` is the reference design for prune/reweight/derive.
- Re-contextualization of vector chunks when their source document changes (versioned,
  mirror of invalidate-don't-delete on the vector side).

## Phase 3 — multifield + routing

Several domain experts (one memory per field), a router that classifies the question,
detects multi-field questions, and — importantly — declines when no expert is competent.
The pluggable-memory interface (ingest/query/update/inspect) is frozen from the current
GraphRAG implementation first; new methods implement it, and the setting selects which
store answers. Same corpus indexed several ways enables the side-by-side comparison that
is itself a deliverable.

## Nice-to-haves (unordered)

- CI (lint + the free test suites on push).
- A RAG-store browser page (inspect chunks/blurbs the way the graph is inspectable).
- Per-conversation domain selector in the chat UI.
- Multi-user beliefs + auth.
- Prompt-caching-aware cost dashboard.

# 12 — Gotchas: the lessons that were paid for

Every entry here was learned by measurement, an outage, or a bug that cost real money or
a day. They are constraints, not opinions — if you want to relitigate one, bring a bench
run. Newest lessons go at the bottom; nothing is ever deleted.

## Fusion: the graph may add, never displace

Cross-store RRF between the vector base and the graph is **degenerate**: their id spaces
never overlap, so "fusion" collapses into a fixed interleave where one-line facts push
out evidence-bearing chunks. Measured on QASPER: evidence recall 0.89 → 0.43, five
rag-correct answers broken, zero rescued. A second idea — graph-corroborated promotion
into the tail chunk slots — also lost (0.61 vs 0.74; fact-*adjacent* ≠ question-relevant).
Hence **supplement fusion**: vector top-k reaches the context identical to rag-alone,
graph facts append through a novelty gate. `tests/test_fusion.py` locks it.

## FalkorDriver binds to one event loop

One `FalkorDriver` per domain, created on the app's loop, cached in
`graph/manager.py` — a second instance (or a per-request TestClient loop) produces
`event loop is closed` errors that look random. Never construct `GraphMemory` outside
the manager in server code. (Uvicorn is fine; `TestClient` per-request loops are not.)

## Graphiti reroutes writes by group_id

Graphiti "helpfully" clones the driver to a database named after the `group_id`. For a
save-key domain (e.g. a bench build writing INTO a checkpoint) that would silently write
into the LIVE base graph. `GraphMemory.__init__` pins `driver.clone` for exactly this
case. Symptom if it regresses: a bench build "succeeds" but the save is empty and your
live graph grew.

## Prompt-cache economics rule the contextualizer

Blurb cost is viable only because the document rides as an **identical prefix** across a
document's chunk calls (≥1,024 tokens, 5–10 min idle TTL, byte-identical or full price).
This is why the doc is FIRST in the prompt, why excerpt-mode batches share one excerpt,
why the first call of each group runs alone before the parallel workers, and why a long
mid-document stall re-pays the prefix write. Change the prompt layout and you 10× the
ingestion bill without touching "functionality".

## The model's input window is a hard ingestion wall

A 522k-token SEC filing exceeds gpt-5.4-mini's usable input (~272k): whole-doc blurbs
hard-fail. `CONTEXT_DOC_CAP` (≈ window − 20k) switches big docs to head+section excerpt
mode. **When the chat model changes, resize the cap** (CLAUDE.md rule). Too high = API
errors mid-build; too low = merely more excerpting.

## Fingerprints exist so money can't lie

`build_skip` reuses any build with the same fingerprint (corpus · cap · extractor ·
embeddings · `_EP_VERSION`). Anything that changes what extraction PRODUCES must bump
`_EP_VERSION` (e.g. `ep700-v2` = document-tuned instructions), or old graphs silently
masquerade as new ones. Query-side changes (search recipe, judge rubric) instead land in
report **provenance**. The rule: same table ⇒ same stamps, no exceptions.

## Judges lie in specific, known ways

`bool("false") is True` — a string verdict once scored every answer correct (hence
`_coerce_bool`, and unparseable ⇒ *unscored*, never confident-wrong). Empty candidates
are infrastructure failures, never judged. Self-judging (no `JUDGE_API_KEY`) inflates
agreement and is flagged in provenance. Gold with "invalid question" needs the rubric's
false-premise rule — a confident direct answer is the WRONG answer there.

## An outage is not a low score

24/46 hybrid answers once failed on connection errors and were scored 0.33 as if wrong —
"hybrid loses" was an outage artifact. Now: error records are excluded from every
quality metric, a breaker pauses after 4 consecutive infra errors, coverage is printed
next to accuracy, and the verdict leads with warnings. If a number looks bad, check
`answered/errors` before believing it.

## Free tiers, pacing, and the tab

`JUDGE_RPM` pacing is opt-in (paid judges run full speed, `JUDGE_CONCURRENCY` wide).
Bench runs are detached jobs — the tab is just a viewer; ⏸ Pause is the real stop.
`uvicorn --reload` kills detached jobs on any file edit (they resume free, but don't
code during a campaign run). Free API tiers may only ever receive **public benchmark
corpora** — never internal documents.

## Corpus quirks that bite

Much of the future prod corpus is **French** (multilingual embeddings + parser required;
blurbs come back in the document's language — correct, don't "fix" it). Some corpus PDFs
are LaTeX with broken ToUnicode maps — embedded text is garbled and needs the
legibility-gated OCR fallback. SEC filings are fine (real text layer) but their tables
flatten roughly.

## Windows is not Linux

`falkordblite`/`redislite` are Unix-only: prod uses `GRAPH_BACKEND=falkor_server`
(external FalkorDB) or Neo4j. Corporate gateways rate-limit harder → lower
`GRAPH_MAX_COROUTINES`. HuggingFace may be blocked → datasets travel as files in the
repo. See RUN_ON_WINDOWS.md for the full list.

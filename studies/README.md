# studies/ — the decision record

Every consequential design decision in Noema traces back to a document in this folder.
Treat it as an append-only ADR log: studies are **superseded, never edited into
something they didn't say** — the history of *why* is part of the deliverable.

| study | decides | date | status |
|---|---|---|---|
| [NOEMA_PLAN_LOG](NOEMA_PLAN_LOG.md) | the running build-decision log, in question order | rolling | living |
| [NOEMA_SOTA_RESEARCH_SUMMARY](NOEMA_SOTA_RESEARCH_SUMMARY.md) | consolidated SOTA findings across all research rounds | rolling | living |
| [NOEMA_PARSING_SOTA](NOEMA_PARSING_SOTA.md) | PDF parsing: Azure DI backbone + vision fallback; Docling local-only | 2026-06-22 | frozen |
| [NOEMA_MEMORY_SOTA](NOEMA_MEMORY_SOTA.md) | memory representation: contextual base first, graph as measured add-on, hybrid over same chunks | 2026-06 | frozen |
| [NOEMA_MEMORY_UX_SOTA](NOEMA_MEMORY_UX_SOTA.md) | how memory/knowledge UX is done across the industry (beliefs, saves, visibility) | 2026-06 | frozen |
| [compass… evolutive survey](compass_artifact_wf-7d8164ae-3320-4481-ae8c-ecd312501c24_text_markdown.md) | external SOTA survey feeding the evolution design | 2026-06 | reference |
| [NOEMA_EVOLUTIVE_MEMORY_READABLE](NOEMA_EVOLUTIVE_MEMORY_READABLE.md) | the plain-language companion to the evolution design | 2026-06 | reference |
| [NOEMA_EVOLUTION_CONTRACT](NOEMA_EVOLUTION_CONTRACT.md) | Phase-2 contract: one goal/invariants/interface/eval-gate for every engine's evolution | 2026-07 | frozen |
| [NOEMA_EVAL_BENCH](NOEMA_EVAL_BENCH.md) | the benchmark design: configs, models, datasets, axes, budgets | 2026-07-06 | frozen |
| [BENCH_DATASETS](BENCH_DATASETS.md) | dataset provenance: CRAG / FinanceBench / Basel-FAQ (+ the humanqa format) | 2026-07-16 | frozen |
| [NOEMA_ARCHITECTURE_STUDY](NOEMA_ARCHITECTURE_STUDY.md) | production organization + handover plan (stages 0/1/2/4; re-nesting rejected) | 2026-07-16 | frozen |

Reading order for a newcomer who asks "why is it built this way": PLAN_LOG →
MEMORY_SOTA → EVAL_BENCH → ARCHITECTURE_STUDY. The measured lessons extracted from all
of these live in [docs/12-gotchas.md](../docs/12-gotchas.md).

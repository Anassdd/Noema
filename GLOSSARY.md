# GLOSSARY.md — the words this project thinks in

Alphabetical. Every conversation about Noema uses these; learn them first.

- **beliefs** — the user's own notes per memory context, injected next to (never into)
  retrieved sources; answers present both sides when they disagree.
- **blurb** (situating context) — the 1–2 sentence LLM-written context prepended to a
  chunk before embedding/BM25 (Anthropic Contextual Retrieval). What makes `rag` "contextual".
- **build** (bench) — the one-time indexing of a prepared corpus into every engine's
  store, identified by its **fingerprint**, checkpointed as a save, reused by `build_skip`.
- **CRAG check** — the pre-answer judge call grading whether retrieved sources suffice;
  failure escalates the retrieval profile and retries.
- **chunk** — a ~512-token structure-aware slice of a document carrying provenance
  (doc, pages, section). The unit of the vector base.
- **config (bench)** — one competitor in a run: `closed_book`, `rag`, `graph`, `hybrid`.
  Same generator, same questions; only retrieval differs.
- **domain / domain_id** — one memory universe (stores are keyed by it; `default` today,
  multi-expert later).
- **Dream** — the graph's self-maintenance pass: merge duplicates, archive stale facts,
  checkpointed and rolled back if an eval gate detects lost knowledge.
- **episode** — Graphiti's ingestion unit: one page of one document, named
  `<file> · p<N>` — which is exactly how graph facts cite their source.
- **evidence recall / overlap** — did retrieval surface the gold evidence? Verbatim
  (recall — unfair to the graph by construction) vs content-words (overlap — fair).
- **excerpt mode** — for documents over `CONTEXT_DOC_CAP`: blurbs are written against
  document head + the chunk's section instead of the whole document.
- **fingerprint** — hash of corpus · cap · extractor · embeddings · episode-version;
  the identity of a build. Different fingerprint = never share a results table.
- **fusion (supplement)** — hybrid's rule: vector top-k intact, graph facts appended
  only when novel. Measured; locked by `tests/test_fusion.py`.
- **gold** — the benchmark's question/answer pairs. *Human gold* ships with the dataset
  (pre-approved); generated gold is drafted by an LLM and human-approved.
- **judge** — the LLM grading answers against gold (cross-family via `JUDGE_*`,
  rubric versioned in provenance). *Self-judge fallback* = generator grading itself
  (flagged, weaker).
- **llmaas** — the prod provider: the company's OpenAI-compatible gateway. Not the
  AzureOpenAI SDK (that branch was deliberately removed).
- **prepare** (bench) — freeze a dataset slice under a token cap: corpus + gold, with
  the all-or-nothing rule (a question enters only if ALL its documents fit).
- **provenance (report)** — the stamps that make numbers comparable: judge models +
  rubric version, scope, graph search recipe, anchoring.
- **resume_key** — identity of a run attempt (fingerprint · configs · model · scope ·
  gold); lets an interrupted run find its own partial records.
- **save** — a named checkpoint of one engine's memory (graph+vector together;
  LightRAG workspace whole). Restoring swaps what answers.
- **scope** — retrieval boundary per question: `auto` = the question's own document when
  gold names one (QASPER, FinanceBench, Basel), corpus-wide otherwise (CRAG).
- **Self-RAG check** — the post-answer judge call grading faithfulness to the sources;
  failure retries with a wider net.
- **suitcase** — the transfer model to the locked-down prod machine: repo + committed
  stores + offline wheels + datasets as files. Why knowledge stores are in git.
- **textgraph** — the dormant instant co-occurrence engine (no LLM). Kept as a possible
  future lens; nothing routes to it.

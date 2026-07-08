# Testing & the lab

This page covers everything under `tests/`: the interactive Streamlit **lab** (a playground
plus per-component inspector pages), two standalone graph playgrounds, the automated test
scripts (which are free and which cost API calls), where results and caches live, and how
to add a new test. The lab is independent of the product — it imports the `backend/app`
modules read-only and the whole `tests/` directory can be deleted without touching the app.
All commands below use the backend virtualenv; provider credentials come from
`backend/.env` (see [Configuration](03-configuration.md)).

## Layout

```
tests/
  lab.py                  # Playground — add documents, ask, get cited answers
  lab_common.py           # shared helpers (report, timing, caching, rendering, "show the code")
  pages/
    1_Parser.py           # Parser         — tabs: How it works | Saved tests | Live run
    2_Chunker.py          # Chunker        — tabs: How it works | Saved tests | Live run
    3_Contextualizer.py   # Contextualizer — tabs: How it works | Saved tests | Live run
    4_Retrieval.py        # Retrieval      — tabs: How it works | Build the base | Ask
  graph_lab.py            # standalone temporal-graph playground (Streamlit)
  graph_workbench.py      # text/PDF → live graph workbench (Streamlit, wide)
  gen_example_pdfs.py     # generates the example PDFs into myTestPDFs/
  myTestPDFs/             # example + user-added PDFs (gitignored)
  results/                # caches, saved runs and the shared test report (details below)
  test_chunking.py        # automated chunker tests            (free)
  test_contextual.py      # automated contextualizer tests     (free, mocked LLM)
  test_textlayer.py       # automated text-route tests         (free)
  test_retrieval.py       # automated retrieval-engine tests   (free, fake embedder)
  test_graph.py           # graph edge-case scenarios          (REAL LLM calls — costs money)
  requirements.txt        # streamlit
```

## Running the Streamlit lab

```bash
backend/.venv/bin/python -m pip install -r tests/requirements.txt
backend/.venv/bin/python -m streamlit run tests/lab.py        # http://localhost:8501
```

The landing page (`lab.py`) is a simple **playground**: add a PDF from the sidebar (or load
the bundled sample story, `resonance_of_sector_7`, from its cached parse — no vision pass,
though ingestion still contextualises and embeds the chunks), ask a question in the chat
box, and read the answer with its cited source passages. It runs
hybrid retrieval (`search_trace`, dense + BM25, rerank off) over the lab's own Chroma store
at `tests/results/rag_store/` and answers with `answer_from`. A "Test report (advanced)"
expander at the bottom summarises every run logged from the inspector pages
(wins / fails / partials).

The sidebar pages are the **inspector**. Each has three tabs:

- **How it works** — a flow diagram of the mechanism, the live thresholds/defaults read
  from the code, and an expander showing the **actual source** of the functions
  (`lab_common.show_source`), so the explanation cannot drift from the code.
- **Saved tests** — browse cached results without re-running anything.
- **Live run** — watch the mechanism execute, with timing (and token cost where relevant).

| Page | What it shows | Cost |
|---|---|---|
| `1_Parser.py` | PDF → Markdown + LaTeX per page. *Saved tests*: cached parses of the example PDFs (rendered pages next to the Markdown); upload your own — it parses once, then is cached. *Live run*: the per-page **routing decision** (text layer vs vision: chars, legibility, math, figure) computed from free signals, plus an optional full parse. | Routing preview is free; a full parse calls the vision model. |
| `2_Chunker.py` | Markdown → provenance-tagged chunks (blocks → sections → pack → overlap). *Saved tests*: seeded use cases and edge cases from `results/chunk_examples.json`, input shown next to the chunks; add your own. | Free — deterministic, no model. |
| `3_Contextualizer.py` | Anthropic-style Contextual Retrieval: an LLM blurb situating each chunk in its document, prepended before embedding/BM25. *Saved tests*: cached examples (original chunk vs the blurb). *Live run*: contextualises live with token cost and timing. | Live run makes one LLM call per chunk. |
| `4_Retrieval.py` | The full retrieval flow. *Build the base*: seed the lab store from cached context runs, ingest cached parses or PDFs, reset. *Ask*: a question flows through dense → BM25 → RRF fuse → optional rerank → top-k context → grounded, cited answer, with every stage visible. | Embeds the query + one answer call; ingestion embeds chunks. |

Every page has a **Log run** control (`lab_common.save_run_button`): it records the run's
input → output with a verdict (`win` / `fail` / `partial`) and a note into the shared
report (`tests/results/test_log.json`), which the Home page displays.

## The graph playgrounds

Two further Streamlit apps run the Graphiti layer directly (not through the HTTP API).
Both need the graph backend available (the default `falkor_local` just works on
macOS/Linux) and use the strong extraction model (`settings.parse_model`, i.e. `gpt-5.4` in
dev) — so **adding knowledge in them costs real LLM calls**.

```bash
backend/.venv/bin/python -m streamlit run tests/graph_lab.py
backend/.venv/bin/python -m streamlit run tests/graph_workbench.py
```

- **`graph_lab.py`** — the temporal knowledge graph, poked at live. Add a sentence and
  watch entities/relationships get extracted (~20–40 s per episode with the strong model);
  add a contradicting one and watch the old fact get **invalidated, not deleted**; ask a
  question and get facts back with their temporal validity windows. A "Load the Kendra
  demo" button ingests three dated episodes (Adidas → Acme → Nike) to demonstrate
  invalidation. The bottom section **replays the saved edge-case runs** from
  `tests/results/graph_runs/` offline — episodes, observations, verdict and the resulting
  graph, no model calls.
- **`graph_workbench.py`** — text or PDF → live knowledge graph → ask & update, in three
  panes (source | live graph | retrieval + corrections). Extraction is bounded by an
  auto-induced per-domain schema (`app/graph/schema.py`): the first build samples the
  source, derives the domain's entity/relationship types, and guides all extraction with
  them. Offers a model picker for the extractor; uses its own domains (`wb_text`,
  `wb_pdf`) so it never touches the product's graph.

## Automated test scripts

Plain Python — no pytest needed. Each file collects its `test_*` functions, prints one
line per test and exits non-zero on failure:

```bash
backend/.venv/bin/python tests/test_chunking.py
backend/.venv/bin/python tests/test_contextual.py
backend/.venv/bin/python tests/test_textlayer.py
backend/.venv/bin/python tests/test_retrieval.py
backend/.venv/bin/python tests/test_graph.py        # costs money — see below
```

| Script | Covers | Cost |
|---|---|---|
| `test_chunking.py` | The Markdown chunker: section paths, size bounding, overlap, giant-paragraph splitting, tiny/empty inputs, page provenance and page-spanning chunks, serialisation, and that oversized atomic blocks (display math, code fences) are **never split** mid-formula. Uses a deterministic word-count tokenizer so results don't depend on tiktoken. | **Free** — no model, no network. |
| `test_contextual.py` | The contextualizer: prompt structure (document-first cacheable prefix, wrapped chunk, temperature 0), blurb assembly onto the chunk, token accounting (incl. `cached_tokens`), empty-context fallback, and `_clean_context` stripping LLM preamble/quotes/fences while preserving real (and French) context. | **Free** — `llm_client.chat` is mocked. |
| `test_textlayer.py` | The free text route of the parser: heading detection, title promotion, re-joining wrapped lines, paragraph breaks, empty input, no false headings. | **Free** — pure functions. |
| `test_retrieval.py` | The retrieval engine: store round-trip (add/count/get), dense search, BM25 exact-term match, RRF fusion via `search_trace` (agreement between retrievers wins), and grounded answer assembly with `[S1]` citations. | **Free** — `llm_client.embed` is patched with a deterministic bag-of-words embedder and `chat` is mocked; store lives in a temp dir. |
| `test_graph.py` | Graphiti edge-case scenarios: temporal invalidation, entity resolution, provenance on retrieved facts, multi-hop retrieval, incremental adds (no rebuild), contentless episodes. | **Costs API calls** — real entity/edge extraction with the strong model (`settings.parse_model` or the chat model). Small 2–3 episode graphs keep it to cents. Needs the graph backend available. |

`test_graph.py` is deliberately not bit-for-bit deterministic: it hard-asserts only
structural invariants (no crash, snapshot returns, edges carry provenance) and records a
**verdict** (`win` / `partial` / `fail`) for the model-dependent behaviour (was the
contradiction invalidated? did two mentions resolve to one node?). Each scenario saves its
episodes, graph snapshot, observations and verdict to
`tests/results/graph_runs/<scenario>.json` — those files are the kept results and feed the
Graph Lab's replay section.

`gen_example_pdfs.py` (needs `reportlab` and `Pillow`) regenerates the example PDFs in
`tests/myTestPDFs/` — each targets a different parser routing outcome (clean prose → free
text layer; tables/formulas/figures/French → vision). Run it once if `myTestPDFs/` is
empty (the directory is gitignored).

## Where results and caches live

Everything is under `tests/results/`:

| Path | What it is | In git? |
|---|---|---|
| `test_log.json` | The shared test report (every "Log run" from the lab pages). | yes |
| `chunk_examples.json` | Seeded chunker use cases + edge cases for the Chunker page. | yes |
| `parser_runs/` | Cached parser results, one JSON per PDF — the Saved-tests tab browses these with **no re-extraction**, and the Retrieval page can ingest from them without re-parsing. | yes |
| `context_runs/` | Cached contextual-retrieval results (chunk + blurb + token costs). | yes |
| `graph_runs/` | Saved edge-case runs from `test_graph.py` (replayable in the Graph Lab). | yes |
| `graph_saved/` | Graph Workbench saves. | yes |
| `graph_schemas/` | Induced per-domain graph schemas (regenerable playground artifacts). | no (gitignored) |
| `graph_store/` | The FalkorDB `.rdb` persistence for the local backend (also the default `GRAPH_DB_DIR`). Regenerable. | no (gitignored) |
| `rag_store/` | The lab's Chroma RAG base (sqlite + HNSW binaries). **Disposable and regenerable** — re-ingest to rebuild; it churns as binary noise in git, hence gitignored. If it is still tracked from an old commit, untrack once with `git rm -r --cached tests/results/rag_store/`. | no (gitignored) |

`tests/myTestPDFs/` is also gitignored (it may hold personal PDFs); regenerate the example
set with `gen_example_pdfs.py`.

## Adding a new test

Follow the existing pattern — a plain, self-runnable file:

1. Create `tests/test_<area>.py`. Put `backend/` on `sys.path` first:

   ```python
   import sys
   from pathlib import Path

   BACKEND = Path(__file__).resolve().parent.parent / "backend"
   sys.path.insert(0, str(BACKEND))

   from app.chunking import chunk_markdown  # noqa: E402
   ```

2. Write `test_*` functions with plain `assert`s and a one-line `print` on success. Keep
   them **free** wherever possible:
   - mock the LLM by swapping `llm_client.chat` (see `test_contextual.py::_patch`);
   - fake embeddings by assigning `llm_client.embed = fake_embed` (see
     `test_retrieval.py`);
   - inject a deterministic tokenizer (`count_tokens=lambda t: len(t.split())`) so size
     assertions don't depend on tiktoken;
   - use `tempfile.mkdtemp()` for any store so runs never pollute `results/`.

3. Copy the runner boilerplate from the bottom of any `test_*.py` — it collects the
   `test_*` functions, reports `N/M passed` and exits `1` on failure:

   ```python
   TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

   if __name__ == "__main__":
       failed = 0
       for t in TESTS:
           try:
               t()
           except AssertionError as e:
               failed += 1
               print(f"  ✗ {t.__name__}: {e}")
       print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
       sys.exit(1 if failed else 0)
   ```

4. If the behaviour under test genuinely needs a real model (as in `test_graph.py`), say
   so in the module docstring, keep the inputs tiny, hard-assert only what does not depend
   on the model, and record a verdict + JSON artefact under `tests/results/` for the rest.

5. To add an **inspector page** instead, create `tests/pages/5_<Name>.py`, import the
   shared helpers from `lab_common` (`style`, `io_banner`, `show_source`,
   `save_run_button`, `timer`), and keep the three-tab structure (How it works | Saved
   tests | Live run) so the lab stays uniform.

## Removing the lab

The lab is designed to delete cleanly:

```bash
rm -rf tests/
backend/.venv/bin/python -m pip uninstall -y streamlit
```

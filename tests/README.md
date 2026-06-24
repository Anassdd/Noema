# Noema — Lab (interactive testbench)

A multipage Streamlit app to inspect each pipeline step. Independent of the product
(imports the app modules read-only) and deletes cleanly.

```
tests/
  lab.py                  # Home — overview + the test report (wins / fails)
  lab_common.py           # shared helpers (report, timing, caching, render, "show the code")
  pages/
    1_Parser.py           # Parser        — tabs: How it works | Saved tests | Live run
    2_Chunker.py          # Chunker       — tabs: How it works | Saved tests | Live run
    3_Contextualizer.py   # Contextualizer— tabs: How it works | Saved tests | Live run
  myTestPDFs/             # example + user-added PDFs (gitignored)
  results/
    test_log.json         # the shared test report
    chunk_examples.json   # seeded chunker use cases + edge cases
    parser_runs/          # cached parser results (Saved tests need no re-extraction)
    context_runs/         # cached contextual-retrieval results
  test_chunking.py        # automated chunker tests (no pytest needed)
  test_contextual.py      # automated contextualizer tests (mocked LLM, free)
  requirements.txt        # streamlit
```

## Run it

```bash
backend/.venv/bin/python -m pip install -r tests/requirements.txt
backend/.venv/bin/python -m streamlit run tests/lab.py        # http://localhost:8501
```

Each tool page has three tabs:

- **How it works** — a flow diagram of the mechanism, the live thresholds/defaults read
  from the code, and an expander with the **actual source** of the functions.
- **Saved tests** — browse results without re-running:
  - *Parser*: cached parse of each example PDF (rendered pages + Markdown, no model call).
    Upload your own PDF — it parses once, then it's cached here too.
  - *Chunker*: the seeded use cases / edge cases, input shown visually next to the chunks.
    Add your own example.
  - *Contextualizer*: cached contextualized examples (original chunk vs the LLM blurb).
    Add your own document.
- **Live run** — watch the mechanism execute with timing:
  - *Parser*: the per-page routing **decision** computed from free signals (no tokens),
    plus an optional full parse.
  - *Chunker*: the stages — blocks → sections → chunks — with sizes and timing.
  - *Contextualizer*: contextualizes live (LLM call per chunk) with token cost and timing.

Every page has a **Log run** control that records the run's input → output (with a
verdict) into the shared report shown on **Home**.

## Automated tests

```bash
backend/.venv/bin/python tests/test_chunking.py      # chunker: normal + edge cases
backend/.venv/bin/python tests/test_contextual.py    # contextualizer: mocked LLM, free
```

## Remove it when done

```bash
rm -rf tests/
backend/.venv/bin/python -m pip uninstall -y streamlit
```

## Background

- Why hosted vision parsing (not local Docling): `NOEMA_PARSING_SOTA.md`, `backend/app/parsing/PARSING.md`.
- Chunking SOTA + mechanism: `backend/app/chunking/CHUNKING.md`.
- Contextual Retrieval method: `backend/app/retrieval/CONTEXTUAL.md`.

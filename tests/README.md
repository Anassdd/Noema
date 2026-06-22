# Noema — Lab (independent test/eval harness)

A standalone place to **validate each pipeline step on real inputs** and see, in a
table, how it behaves — speed, output, and weak points. It is separate from the
app: it imports the backend modules but ships its own fixtures and runners, so it
never affects the running product.

The pipeline is built in steps (parse → chunk → embed → retrieve → …). Each step
gets its own folder here as it lands. Today: **parse (Docling)**.

```
tests/
  lab.py                 # interactive Streamlit app — drop a PDF, flip OCR, see it parse
  fixtures/
    make_fixtures.py     # generates the edge-case PDFs (deterministic)
    pdfs/                # generated fixtures (gitignored)
  docling/
    run.py               # headless: runs Docling over every fixture, times + scores it
  results/
    docling_report.md    # the reproducible benchmark table + findings
    study.md             # your curated runs, appended from the lab ("Save to study")
    markdown/            # each fixture's parsed Markdown output
    screenshots/         # PNG render of each fixture's first page
```

## Run it

Uses the backend venv. One-time setup:

```bash
backend/.venv/bin/python -m pip install -r tests/requirements.txt
backend/.venv/bin/python tests/fixtures/make_fixtures.py   # build the edge-case PDFs
```

**Interactive lab** (play with it, then "Save to study"):

```bash
backend/.venv/bin/python -m streamlit run tests/lab.py
# opens http://localhost:8501
```

**Headless benchmark** (the reproducible report table):

```bash
backend/.venv/bin/python tests/docling/run.py     # writes tests/results/docling_report.md
```

## Remove it when done

Self-contained — nothing in the app depends on it:

```bash
rm -rf tests/
backend/.venv/bin/python -m pip uninstall -y streamlit reportlab
```

## What the Docling step is tested against

| Fixture | What it validates |
| --- | --- |
| `simple` | Plain digital text — baseline correctness |
| `multipage` | Page count / provenance across pages |
| `headings` | Document structure → Markdown headings |
| `table` | Table reconstruction (Docling's headline feature) |
| `long` | Throughput on a bigger doc (sec/page) |
| `empty` | Blank page → clean "no content" error |
| `scanned` | Image-only page → OCR behavior |
| `not_a_pdf` | Garbage bytes → rejected, not crashed |
| `truncated` | Corrupted PDF → rejected, not crashed |

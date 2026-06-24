# Parsing — how Noema turns a PDF into Markdown

This package is the **only** thing in the app that knows how to read a PDF. Everything
downstream (chunking, embedding, the graph) consumes the Markdown it produces. The rest
of the app calls exactly one function and never cares which backend ran:

```python
from app import parsing
doc = parsing.parse_document(data, filename)   # -> ParsedDoc
```

**Input:** a PDF file (`bytes`). &nbsp;
**Output:** Markdown + LaTeX per page (`ParsedDoc`, with page provenance).

## Package layout

| File | Role |
|---|---|
| `__init__.py` | Public API: `parse_document`, `ParsedDoc`, `ParseError`. Import from here. |
| `dispatch.py` | The seam — picks the backend from the `PARSER` env var. |
| `vision.py` | **Vision backend** (default): render page → vision LLM, with per-page routing. |
| `docintel.py` | **Azure Document Intelligence backend**: deterministic, in-tenant. |
| `base.py` | Shared types (`ParsedDoc`, `ParseError`) both backends return. |

The backend is chosen by config, not by the caller — switching dev → prod is a `.env`
change, no code change (this mirrors the LLM provider abstraction).

```
PARSER=vision     # default, works on the Mac and on Azure
PARSER=docintel   # Azure Document Intelligence (needs DOCINTEL_ENDPOINT + DOCINTEL_KEY)
```

---

## How the vision backend works (the default)

It walks the PDF **one page at a time** and sends each page down the cheapest path
that won't lose information:

```
                ┌─────────────────────────── per page ───────────────────────────┐
                │                                                                  │
  page ─▶ read the embedded text layer (free, local)                              │
                │                                                                  │
                ▼                                                                  │
        Is it clean prose AND figure-free?                                         │
          • ≥ 200 chars of text                                                    │
          • ≥ 85% letters/whitespace (catches garbled / broken-font)              │
          • no math/LaTeX/symbol signal                                            │
          • no image ≥ 3% of the page, and < 15 vector drawing objects            │
                │                                   │                              │
            yes │                               no  │                              │
                ▼                                   ▼                              │
        ┌──────────────┐                  render page → PNG (pypdfium2, light)     │
        │ TEXT route   │                  → vision LLM transcribes to Markdown     │
        │ 0 tokens,    │                  → Markdown + LaTeX + figure descriptions │
        │ instant, free│                  ┌──────────────┐                         │
        └──────────────┘                  │ VISION route │ (a few cents/page)      │
                                          └──────────────┘                         │
                └──────────────────────────────────────────────────────────────────┘
```

The decision is **automatic** — there are no flags to set in normal use. The vision call
goes through `llm_client`, so it's OpenAI on the Mac and Azure in prod by `.env` alone.

### Why "figure-free" matters
The text-layer check only sees *text*. A diagram contributes no text, so a page with a
long paragraph **and** a chart would otherwise be judged "clean prose" and the chart
silently dropped. The figure check (`_has_figure`) inspects the page's actual objects —
raster images and vector drawings — and forces such a page to vision so nothing is lost.

---

## How the DI backend works (the prod backbone)

`docintel.py` sends the whole PDF to Azure Document Intelligence's `prebuilt-layout`
model and gets back Markdown (tables as HTML, formulas as LaTeX) with page-level
provenance. It is **deterministic** (no hallucination) and stays **inside the company's
Azure tenant**. It's the recommended backbone for citation-grade answers; the vision
backend is the fallback for the pages DI handles poorly.

> **Status:** wired and import-verified, but **not yet run against a live DI resource**
> (there isn't one on the dev Mac). Validate on the company endpoint before relying on it.

---

## Case scenarios — what happens

| The page is… | Route | What you get | Cost |
|---|---|---|---|
| Clean digital prose | **text** | text layer → light Markdown (headings + paragraphs) | free |
| A formula / math-heavy page | **vision** | formulas as LaTeX `$…$` / `$$…$$` | paid |
| A normal table | **vision** | a Markdown (or HTML) table | paid |
| **Text-dominated + a diagram** | **vision** | the prose **plus** a detailed *[Figure: …]* extraction (labels, trend/flow, readable values) | paid |
| A scanned / image-only page | **vision** | OCR-quality transcription | paid |
| Broken-font / bad-ToUnicode (LaTeX PDFs) | **vision** | correct text (the garbled layer is ignored) | paid |
| French text (accents, é/è/ç, Hölder) | either | preserved exactly, never translated | — |
| Tiny ~4pt micro-text / faint watermark | **vision** | ⚠️ may be **silently misread** (see below) | paid |
| A non-PDF file (`.docx`, image) | — | rejected at upload (`400`) | — |

**Multi-page docs mix routes.** A 10-page report might come back as 6 `text` + 4 `vision`
— the savings scale with how prose-heavy the document is. A math-heavy corpus routes most
pages to vision.

---

## Advantages

- **Hardware-independent.** Nothing heavy runs locally — page rendering is light
  (`pypdfium2`), the actual reading is a hosted model call. Runs fine on a locked-down,
  weak corporate PC. (This is why we dropped local Docling — see `NOEMA_PARSING_SOTA.md`.)
- **Handles any PDF**: digital, scanned, broken-font, French, math, tables, figures.
- **Math → LaTeX, and figures *extracted*** (type, labels, trend/flow, readable values),
  not dropped — important for a research corpus where the figure is often the result.
- **Dev → prod is one `.env` line.** Same code on Mac (OpenAI) and Azure; and a second
  axis (`PARSER`) swaps the whole parser to deterministic Azure DI with no code change.
- **Page-level provenance for free** (`page_markdown` is per page) — the seam citations
  build on.
- **Cost-aware**: clean prose pages cost nothing; you only pay where it's genuinely hard.

## Bad points / limitations

- **Ultra-small / faint text** (~4pt, watermarks) can be **silently misread** — the API
  downsamples a full page to ~768px, so sub-resolution glyphs aren't recoverable, and a
  wrong reading looks confident. This is the one real failure the stress test exposed.
- **Hallucination risk** is inherent to any vision transcription. Mitigated by a strict
  "transcribe exactly, never invent, `[illegible]` if unreadable" prompt — but not zero.
  The DI backbone exists precisely to remove this for citation-grade work.
- **Figures are extracted as text, not as the image.** A figure becomes a detailed
  faithful description — type, all labels/units, the trend or the A→B→C flow, and values
  the model can actually read — so questions about it can be answered. But it is still a
  *textual* extraction bounded by page resolution: tiny labels may be `[illegible]`, and a
  complex diagram's exact node/edge graph isn't perfectly structured (relevant for the graph
  layer). It will not fabricate values that aren't shown.
- **All-or-nothing per page.** A mostly-text page with one figure costs a full vision call
  (the text is re-transcribed too) — no hybrid text-layer-prose + vision-only-figure.
- **A tiny, simple vector diagram** (< 15 path objects, no raster) can slip to the text
  route and be dropped. Real diagrams clear the threshold easily; it's tunable.
- **DI backbone is unproven** against a live resource (see status note above).
- **PDF only** today — other formats are rejected.

---

## Parked optimizations (future, not built)

- **Region-level crop hybrid.** For a *clean-prose + raster-figure* page, take the
  prose from the free text layer and send only a **crop of the figure** (we already
  have its bounding box) to vision, instead of a full-page call — fewer image tiles,
  cheaper. Parked because: it only helps that one page shape (scanned / broken-font /
  math / vector-figure pages have **no** isolable region — the "necessary part" *is*
  the whole page); the general version needs a heavy **layout-detection model** we
  deliberately avoided (the reason we dropped Docling); and stitching regions back
  into correct reading order re-introduces layout analysis. Whole-page is also what
  the frontier agents do and preserves reading order + cross-region context for free.
  Revisit only if the real corpus turns out to be mostly "clean text + isolated
  figures" *and* vision cost becomes a concern — measured, not assumed.
- **Office formats** (`.docx` / `.pptx`). Add a backend behind `parse_document`
  (Azure DI ingests Office natively, or lightweight `python-docx` / `python-pptx` for
  a text-only path). For now, export to PDF. The seam is already in `dispatch.py`.

---

## Output shape (`ParsedDoc`)

```python
doc.filename        # str
doc.pages           # pages processed
doc.total_pages     # pages in the file
doc.page_markdown   # list[str] — Markdown per page (provenance)
doc.markdown        # str — all pages joined
doc.routes          # list[str] — "text" | "vision" | "docintel" per page
doc.prompt_tokens, doc.completion_tokens, doc.total_tokens
doc.text_pages, doc.vision_pages   # how many took each route
```

## Tuning knobs (`vision.py`)

| Constant | Default | Meaning |
|---|---|---|
| `_MIN_TEXT` | 200 | min chars for a page to count as "has real text" |
| `_MIN_LEGIBILITY` | 0.85 | min fraction of letters/whitespace (catches garbled fonts) |
| `_MIN_IMG_AREA` | 0.03 | a raster image this fraction of the page → treat as a figure |
| `_MAX_PROSE_PATHS` | 15 | this many vector drawings → treat as a chart/diagram/table |

## Try it
The Streamlit lab (`tests/lab.py`) lets you drop any PDF and watch the routing live,
per page, with the rendered image next to the parsed Markdown:

```
backend/.venv/bin/python -m streamlit run tests/lab.py
```

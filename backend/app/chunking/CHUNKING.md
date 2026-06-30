# Chunking — how Noema turns parsed Markdown into retrievable chunks

This package is the **"chunk"** step of the ingestion pipeline (`parse → chunk →
extract → store`). It takes the parser's Markdown and cuts it into small, **provenance-
tagged passages** that everything downstream (embedding, retrieval, the graph) consumes.

```python
from app.chunking import chunk_parsed_doc, chunk_markdown
chunks = chunk_parsed_doc(parsed_doc)     # ParsedDoc -> list[Chunk], with page provenance
chunks = chunk_markdown(markdown_string)  # raw Markdown -> list[Chunk], no page info
```

**Input:** Markdown (`str`) — or a `ParsedDoc` for page provenance. &nbsp;
**Output:** `list[Chunk]` (text + `{doc, page(s), section, tokens}`).

## Package layout

| File | Role |
|---|---|
| `__init__.py` | Public API: `chunk_parsed_doc`, `chunk_markdown`, `Chunk`. |
| `markdown_chunker.py` | The structure-aware recursive chunker. |
| `base.py` | The `Chunk` type (text + provenance). |
| `tokens.py` | Token counter — exact via tiktoken if present, else a heuristic; **injectable**. |

## Why this method (the SOTA we landed on)

Research (mid-2026) is blunt: **the cut is low-leverage.** Recursive structure-aware
splitting at ~512 tokens is the top performer; **semantic/embedding chunking is slower
(~14×) and not consistently better.** The real accuracy gains come *after* the cut
(contextual retrieval, −49/−67%). So the chunker stays simple and fast, and spends its
care on **structure** and **provenance**, not on a clever boundary detector.

## How it works (per document)

```
Markdown ─▶ split into BLOCKS (heading | paragraph | list | code | $$math$$ | table)
            each block keeps its char span (for page mapping)
        ─▶ group blocks under their HEADING PATH      ("Methods › Data")
        ─▶ PACK blocks into chunks up to `target_tokens`
              • a block bigger than target → split recursively:
                   paragraphs → sentences → hard char windows
              • atomic blocks (code, $$…$$, <table>) are NEVER split
        ─▶ add `overlap_tokens` from the previous chunk (same section only)
        ─▶ fold a too-small trailing chunk (< `min_tokens`) into the previous one
        ─▶ tag each chunk: {doc, page(s), section, token_count, overlap}
```

The decision is **automatic** — no per-document tuning needed. **LaTeX is kept inline**
as text (good for embedding and the later entity extraction).

### Where page provenance comes from
`chunk_parsed_doc` joins the parser's **per-page** Markdown while remembering each page's
character range. A chunk's `pages` are the pages its content spans — so a chunk that
straddles a page break cites **both** pages. (`chunk_markdown` on raw text has no page
info → `pages = []`.)

## Case scenarios — what happens

| Input | Result |
|---|---|
| Multi-section paper | one+ chunk per section; `section` = heading path; pages tagged |
| Page-spanning paragraph | one chunk citing **both** pages |
| A heading with lots of prose | split into several ~`target`-token chunks, all in that section |
| A giant paragraph, no structure | recursively split by sentences, each ≤ target |
| A display formula `$$…$$` | kept **whole** inside its chunk, never split mid-formula |
| A table (Markdown or `<table>`) | kept **whole** as one atomic block |
| Fenced code with blank lines | kept **whole** (blank lines inside don't split it) |
| French text (accents) | preserved verbatim |
| Tiny doc | exactly one chunk |
| Empty / whitespace | **zero** chunks (no crash) |

## Advantages

- **Fast, cheap, deterministic** — no model call, no GPU; runs anywhere (fits the
  locked-down prod box).
- **Structure-aware** — cuts on real headings/paragraphs, beating naive fixed-size by
  ~5–10 points on structured docs; sections carried in metadata.
- **Provenance built in** — every chunk cites `{doc, page(s), section}`, the foundation
  for grounded citations.
- **Atomic-safe** — formulas, tables, and code are never mangled.
- **Tunable + injectable** — `target_tokens` / `overlap_tokens` / `min_tokens`, and a
  pluggable token counter (so it never hard-depends on a downloadable vocab).

## Limitations / known edges

- **Text-route structure is heuristic** — when the *parser* routes a page to the free
  text layer, headings are recovered by a light **text-only** heuristic (short, title-like
  lines that start like a title and have no sentence punctuation), not by font size, so an
  unusual heading may be missed. Vision-routed pages get exact headings from the model.
  Even if a line is mis-promoted, the chunker keeps the heading text **in the chunk body**
  (not only in the section path), so no character is ever dropped from retrieval. (A parser concern.)
- **Token counts are approximate** when tiktoken isn't installed (heuristic ~4 chars/tok);
  exact with tiktoken. Either way it's used only to size chunks, so slight drift is fine.
- **Markdown tables are grouped as one block** by blank-line boundaries; an unusually
  large table can exceed `target_tokens` (kept whole on purpose).
- **No semantic/topic splitting** — deliberate (not worth the cost); revisit only if eval
  shows it helps your corpus.

## Output shape (`Chunk`)

```python
chunk.chunk_id        # "paper.pdf::3"
chunk.doc_id          # source document
chunk.index           # 0-based order within the document
chunk.text            # the passage (incl. any overlap prefix)
chunk.header_path     # ["Methods", "Data"]   ·  chunk.section -> "Methods › Data"
chunk.pages           # [4]  or  [4, 5] if it spans a page break
chunk.token_count, chunk.char_count
chunk.overlap_tokens  # leading tokens carried from the previous chunk
chunk.domain_id       # "default" for now (multi-domain later)
chunk.to_dict()       # JSON-friendly
```

## Tuning knobs

| Param | Default | Meaning |
|---|---|---|
| `target_tokens` | 512 | size to pack chunks up to (the SOTA sweet spot) |
| `overlap_tokens` | 64 | tokens carried from the previous chunk (boundary safety) |
| `min_tokens` | 64 | a trailing chunk smaller than this merges into the previous |
| `count_tokens` | tiktoken/heuristic | injectable token counter |

## Try it
The chunker has its own page in the test lab — drop Markdown or a PDF and inspect every
chunk's text, section, pages, and overlap live:

```
backend/.venv/bin/python -m streamlit run tests/lab.py     # → "Chunker" page
```

## Tested
`tests/test_chunking.py` covers normal + edge cases (size-bounding, header nesting,
formula/table preservation, overlap, page provenance incl. page-spanning, empty/tiny).
Run: `backend/.venv/bin/python tests/test_chunking.py`.

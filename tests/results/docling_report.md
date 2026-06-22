# Docling parse — test report

_Generated 2026-06-22 12:08 · docling 2.104.0 · Python 3.14.2 · arm64 CPU_

| Case | Validates | Pages | Chars | Time | Result | Notes |
| --- | --- | ---: | ---: | ---: | :---: | --- |
| `simple` | Plain digital text — baseline | 1 | 230 | 3.58s | PASS | 230 chars |
| `multipage` | Page count across pages | 3 | 643 | 1.06s | PASS | 3 pages, 0.35s/page |
| `headings` | Structure -> Markdown headings | 1 | 307 | 0.12s | PASS | 6 Markdown heading marks |
| `table` | Table reconstruction | 1 | 14 | 0.12s | PASS | table region classified as IMAGE — text lost |
| `long` | Throughput on a bigger doc | 12 | 9961 | 1.95s | PASS | 12 pages, 0.16s/page |
| `empty` | Blank page -> clean error | — | — | 0.12s | PASS |  |
| `scanned` | Image-only page -> OCR engine | 1 | 78 | 4.85s | ℹ︎ ok | OCR produced 78 chars |
| `not_a_pdf` | Garbage bytes rejected | — | — | 0.00s | PASS |  |
| `truncated` | Corrupted PDF rejected | — | — | 0.00s | PASS |  |

## Speed & efficiency

- **Cold start (one-time per process):** 4.5s to build the converter, then the first parse adds ~3.6s of warmup.
- **Steady-state (digital text):** 0.16s/page (the 12-page doc).
- **OCR pages cost more:** the scanned page took 4.8s for 1 page.
- Runs on **CPU**; the per-page cost is the layout model on each page render.

## Findings

- On the **synthetic** vector table, Docling classified the region as an image (`<!-- image -->`) and dropped the text — a silent-content-loss failure mode. Validate on a real research-paper table before judging; likely a fixture artifact.
- OCR is **opt-in** (off by default for speed); with `engine='ocr'` the image-only page yielded 78 chars.
- Bad input is rejected cleanly (no crash): empty, not_a_pdf, truncated.
- Cold start (model load) dominates a single parse — fine for batch ingestion, a one-time cost per process. First run downloads models (layout from HuggingFace; OCR models from ModelScope only when OCR is on) — a prod-network risk to pre-stage.
- Not yet tested: math→LaTeX, multi-column reading order, encrypted PDFs.

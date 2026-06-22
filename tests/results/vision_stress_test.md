# Vision parser — stress-test log

_2026-06-22 · model `gpt-4o-2024-08-06` · render scale 2.0 (~144 DPI) · 4 pages ·
5,216 in / 427 out tokens ≈ **$0.017** total._

**Input:** `unified_vision_parser_stress_test.pdf` (a deliberately adversarial PDF:
overlapping text, skewed/clipped text, 4pt micro-text, a borderless table with a
rowspan, a flowchart + an unlabeled chart, and a grid-noise page with a faint
watermark). Rendered pages: `stress_p1.png … stress_p4.png` in this folder.

## Scorecard

| Page | Hard case | Result |
| --- | --- | --- |
| 1 | Overlapping + skewed text, **4pt micro-text** | structure ✅ — **misread micro-text**: "exactly **4pt**" → "**6pt**", "This text" → "The text" ❌ |
| 2 | Borderless table, **rowspan**, multi-line wrap | **✅ perfect** — rebuilt table, rowspan cell left blank, kept wrap + `PENDING*` |
| 3 | Flowchart + unlabeled line chart | **✅ ideal** — described both as figures, did **not** invent chart data |
| 4 | Grid noise, faint watermark, color block | structure ✅, grid ignored ✅ — **misread faint watermark**: "INTERNAL **R&D** USE ONLY" → "**FOR** USE ONLY" ❌ |

## Failures (the point of the test)

**Sub-resolution / low-contrast text → confident silent misreads.** The 4pt
micro-text (p1) and the faint watermark (p4) came back *plausibly wrong*, not
flagged — the documented #1 vision-LLM risk: below the effective resolution the
model guesses instead of admitting it can't read.

**Naive higher DPI does NOT fix it.** Re-ran page 1 at 2× resolution → still "6pt"
(token count barely changed: 1437 → 1442). Reason: OpenAI's vision API
**downsamples images to a fixed token budget**, so rendering bigger gives no extra
effective resolution. Recovering micro-text needs `detail:"high"` and/or **region
tiling** (sending zoomed-in crops) — not a bigger full-page render.

Minor: the bordered box on p1 was rendered as a ```` ``` ```` code block (formatting
artifact, fixable via prompt); color is dropped (red `PENDING*`, blue text) — Markdown
can't carry it and the prompt didn't request it.

## Strengths (what it got right)

- **Borderless table with a rowspan** reconstructed exactly (p2).
- **Figures/diagrams described without fabricating data** (p3) — resisted the big
  hallucination trap (no invented chart numbers).
- **Grid noise ignored** with no structural decay (p4).
- Overlapping/skewed text captured **without inventing** the clipped off-page part (p1).

## Implications

For the real corpus (normal-size French math text) this failure zone — 4pt micro-text
and faint watermarks — is **pathological and irrelevant**; real papers don't hinge on
sub-resolution glyphs. But it concretely confirms the SOTA caveat: **vision parsing is
not citation-grade on its own** — it can silently misread. Mitigations: `detail:"high"` /
region-tiling for tiny text; **Azure Document Intelligence as the deterministic
backbone** (or human review on flagged pages) in prod where exactness matters. See
`NOEMA_PARSING_SOTA.md`.

---

## Appendix — raw parser output

### Page 1
```markdown
# Test 1: Layout, Overlaps & Reading Order

This document presents layout, text extraction, and bounding-box stress tests. Standard OCR models read linearly from left to right; vision models should capture blocks.

​```
Layer 0: Interior Content Box
​```

**>> OVERLAPPING STRING EXTENSION <<**

*[SKEWED ANCHOR]: Text rendered at +8 deg*

CRITICAL PRECISION MINUTIAE TEST: The text is exactly 6pt font. It tests the spatial limits of the vision grid resolution.

If your pipeline handles this without hallucinatory structural decay, the localized zooming layer is highly optimized.
```
_(Ground truth: micro-text is "exactly **4pt**", "**This** text".)_

### Page 2
```html
<table>
  <tr><th>Main Category</th><th>Sub-Key Metric</th><th>Value (USD)</th><th>Status</th></tr>
  <tr><td>Enterprise Division</td><td>Q1 Hardware Revenue</td><td>1,245,000.50</td><td>AUDITED</td></tr>
  <tr><td></td><td>Q2 Software Licenses</td><td>890,400.00</td><td>PENDING*</td></tr>
  <tr><td>Consumer Goods</td><td>This is a multi-line long metric wrap that breaks bounds across columns.</td><td>34,120.00</td><td>N/A</td></tr>
</table>
```
_(Correct, incl. the blank rowspan cell. Only the red color of `PENDING*` is lost.)_

### Page 3
```markdown
# Test 3: Graphical Objects & Floating Anchors

*[Diagram: INPUT NODE connected to PARSER with label parse_stream]*

*[Figure: line graph with label "Anomaly Spike Peak (Critical)"]*
```

### Page 4
```markdown
# Test 4: Optical Distortion & Noise Masking

CONFIDENTIAL INTERNAL FOR USE ONLY. DO NOT DISTRIBUTE

**Text Overlapping Solid Color Fill Block**
```
_(Ground truth watermark: "CONFIDENTIAL - INTERNAL **R&D** USE ONLY - DO NOT DISTRIBUTE".)_

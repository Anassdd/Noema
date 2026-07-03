# Noema — PDF Parsing SOTA (Azure-only, no heavy local compute, math-heavy)

_Deep-research synthesis, 2026-06-22. 22 sources fetched, 25 claims adversarially
verified (24 confirmed, 1 refuted). Method: fan-out web search → fetch → 3-vote
verification → synthesis. This supersedes the "Docling local" assumption in
`NOEMA_PLAN_LOG.md` Stage B for the **prod** environment._

## TL;DR

Parse behind **one `Parser` interface** (mirrors the LLM provider seam), with a
**two-track** backend selected by `.env`:

1. **Backbone / default (prod): Azure AI Document Intelligence v4.0 Layout** +
   the **`ocr.formula` add-on** → Markdown (tables as HTML), formulas as **LaTeX**,
   and **deterministic page + bounding-polygon provenance** for every element.
   Fully in-tenant / in-region. Deterministic = no hallucination.
2. **Fallback (hard pages): Azure OpenAI vision** model (a *strong* GPT-4o/4.1-class
   deployment) → render page to image → prompt for Markdown + LaTeX. For
   broken-font, dense-math, complex multi-column pages.
3. **Optional 3rd, in-tenant: Mistral OCR on Azure AI Foundry** (serverless,
   network-isolated, in-region) — but its math/LaTeX fidelity is **unproven**
   (a marketing claim was refuted), so benchmark before trusting it for formulas.
4. **Docling** drops to a **local/offline fallback only** (air-gapped or strong
   dev box) — not the default, because it needs heavy installs + a strong machine.

This satisfies all four constraints: **no heavy local compute** (all hosted),
**stays in the Azure tenant** (DI + Azure OpenAI + Mistral-on-Foundry are in-region),
**dev→prod = `.env` swap**, and **citation-grade provenance** (DI) — which your plan
requires for grounded answers.

## Why DI is the backbone, vision is the fallback (not the reverse)

DI gives **deterministic, per-element page number + polygon coordinates** — the
citation backbone a grounded RAG/graph pipeline needs. The vision route has **no
inherent provenance** and can **silently misread** digits/Greek letters. So: DI for
the bulk + provenance; vision only for pages DI handles poorly, with its output
grounded/cross-checked.

## The math evidence (this is the big shift)

Independent benchmark **arXiv:2512.09874** (Horn & Keuper, ICPR 2026; 2,052
formulas, LLM-as-judge, human-validated r=0.78):

| Parser | Formula → LaTeX (0–10) |
| --- | ---: |
| Qwen3-VL-235B (open VLM) | **9.76** |
| Gemini 3 Pro | 9.75 |
| PaddleOCR-VL (0.9B, open) | 9.65 |
| **Mathpix** (dedicated math-OCR) | 9.64 (rank 4) |
| pypdf | 7.69 |
| GPT-5-mini | 6.61 |
| GROBID | 5.70 |

**Takeaways:** (a) dedicated math-OCR (Mathpix) is **no longer uniquely best** —
frontier vision-LLMs match/beat it; (b) **model choice is load-bearing** — the
vision-LLM category spans 6.61→9.76, so you must pin a *strong* vision deployment,
not "any" GPT. Tables (separate benchmark arXiv:2603.18652, March 2026): Gemini 3
leads, beating specialized OCR (table-only, medium confidence).

## What the big agents actually do (and why it validates the vision track)

All three frontier vendors converge on **"render each page to an image → feed the
vision model, hybrid with extracted text"** — *not* a separate OCR pipeline:

- **Claude:** converts each page to an image **and** extracts its text; both go to
  the model (vision-based, hybrid).
- **OpenAI (vision PDF route):** extracts **both text and page images** and sends
  both; requires a vision-capable model.
- **Gemini:** native multimodal — pages as images (~258 tokens/page), preserves
  layout, transcribes text/tables/diagrams.
- **OpenAI Assistants File Search (the retrieval-only extreme):** text-only,
  explicitly does **NOT** parse images/charts/tables.

So the frontier is **vision-first hybrid** — which is exactly the Azure OpenAI
fallback track. But it imports the risk: hallucination + no provenance.

## Trade-offs & mitigations

- **Hallucination (the core risk):** vision LLMs silently misread; "even high-scoring
  parsers occasionally produce severe errors." → DI provenance as backbone,
  confidence thresholds, human review on flagged pages.
- **Cost:** DI formula/high-res are **paid add-ons (~$6 / 1,000 pages)** on top of
  base Layout; vision per-page cost scales with image+text tokens (can exceed DI on
  long docs). → route cheap-deterministic-first, vision only when needed.
- **Mistral OCR:** qualifies on privacy/deployability; math/LaTeX fidelity **refuted
  / unproven** → don't rely on it for formulas without your own test.

## The big caveat — read before locking anything

The two headline benchmarks use **SYNTHETIC, machine-rendered LaTeX PDFs** with
clean ground truth. They explicitly do **NOT** cover scanned, broken-font,
multi-column reading order, or **French/multilingual** docs — i.e. **not your exact
corpus** (`resume_af.pdf` = broken-font French math). So those dimensions rest on
capability/architecture reasoning, **not** measured numbers. **Pilot the two Azure
tracks on your real corpus before fixing the default.**

## Open questions / next steps

1. **Pilot** Azure DI (+formula add-on) vs Azure OpenAI vision on *real* scanned /
   broken-font / French papers — no benchmark covers this.
2. **Cost & latency**: DI-stack vs vision-per-page on representative docs → set the
   routing threshold between backbone and fallback.
3. **Which Azure OpenAI vision deployment** is available *and* strong in the company
   tenant (the top VLMs — Qwen3-VL, Gemini 3 — won't be inside Azure-only).
4. **Provenance for vision output**: how to attach DI page/polygon provenance to
   vision-generated Markdown so citations stay trustworthy when the fallback runs.

## Key sources

- Azure DI v4.0 Layout — Markdown + HTML tables + provenance: learn.microsoft.com/azure/ai-services/document-intelligence/prebuilt/layout
- DI add-on capabilities (formula → LaTeX, paid): .../document-intelligence/concept/add-on-capabilities
- DI for RAG: .../document-intelligence/concept/retrieval-augmented-generation
- DI data privacy/residency: learn.microsoft.com/azure/foundry/responsible-ai/document-intelligence/data-privacy-security
- Formula benchmark (ICPR 2026): arxiv.org/abs/2512.09874 · code: github.com/phorn1/pdf-parse-bench
- Table benchmark: arxiv.org/html/2603.18652v1
- Mistral OCR on Azure Foundry: techcommunity.microsoft.com/blog/azure-ai-foundry-blog/unlocking-document-intelligence-mistral-ocr-now-available-in-azure-ai-foundry/4401836
- Claude PDF support: platform.claude.com/docs/en/build-with-claude/pdf-support
- OpenAI PDF files (vision): developers.openai.com/api/docs/guides/pdf-files
- Gemini document processing: ai.google.dev/gemini-api/docs/document-processing
- OpenAI Assistants File Search (text-only limit): platform.openai.com/docs/assistants/tools/file-search

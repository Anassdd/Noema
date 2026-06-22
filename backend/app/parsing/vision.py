"""Vision parser — the default backend (with tiered routing).

Each page is handled by the cheapest path that's safe:
  - **text** : only if the page is confidently plain prose AND carries no figure —
    a clean, legible, prose-only text layer with no images/drawings. We use that
    text directly — free, instant, no vision call.
  - **vision**: anything harder (garbled/scanned/broken-font, any math/table signal,
    or a page that contains an image/figure/chart) — we render the page to an image
    (pypdfium2, light) and a vision LLM transcribes it to Markdown + LaTeX.

The route is decided PER PAGE and is fully automatic — no flags to set. The visual
check (images + vector drawings) means a page mixing prose with a figure goes to
vision, so the figure is never silently dropped.

The vision call goes through the provider abstraction (llm_client), so OpenAI on
dev and Azure in prod are a single `.env` switch. Page-level provenance is free.
See PARSING.md for the full picture; NOEMA_PARSING_SOTA.md for why (not local Docling).
"""

from __future__ import annotations

import base64
import re
from io import BytesIO

from app import llm_client
from app.parsing.base import ParseError, ParsedDoc

PROMPT = (
    "You are a precise document-transcription engine. Transcribe THIS PAGE image to "
    "clean GitHub-Flavored Markdown.\n"
    "Rules:\n"
    "- Output ONLY the transcription — no preamble, no commentary, no surrounding code fence.\n"
    "- Preserve reading order and structure: headings as #/##, lists, bold/italic.\n"
    "- Render EVERY mathematical formula as LaTeX: inline $...$, display $$...$$.\n"
    "- Render tables as Markdown tables; use an HTML <table> only when cells are merged.\n"
    "- For a figure, diagram, drawing, or chart, insert a short italic description in "
    "square brackets, e.g. *[Figure: bar chart of revenue vs year]* — never invent its data.\n"
    "- Transcribe text EXACTLY as it appears, in its ORIGINAL language (e.g. French) with "
    "all accents. Do NOT translate, summarize, correct, or add anything.\n"
    "- If part of the page is unreadable, write [illegible]."
)

# A page is routed to the free text layer only if it's clearly clean prose: enough
# text, mostly letters/whitespace, and NO math/table/figure signal (those need vision).
_MIN_TEXT = 200
_MIN_LEGIBILITY = 0.85
_MATH = re.compile(r"[∑∫√≤≥≠±×÷∞∂∇°·]|\\[a-zA-Z]+|\$|\^\{|_\{|\\frac|\\sum|\\int")

# A page also goes to vision if it carries a figure the text layer can't represent:
# a raster image covering at least this fraction of the page, or this many vector
# path objects (charts / diagrams / ruled tables). Calibrated on the test corpus —
# prose pages showed <=8 paths, a vector figure page showed >100; tune if needed.
_MIN_IMG_AREA = 0.03
_MAX_PROSE_PATHS = 15


def _legibility(text: str) -> float:
    if not text:
        return 0.0
    return sum(c.isalpha() or c.isspace() for c in text) / len(text)


def _is_clean_prose(text: str) -> bool:
    """True only if the page is confidently plain prose the text layer can be
    trusted for — anything math/structured falls through to vision."""
    t = text.strip()
    if len(t) < _MIN_TEXT:
        return False
    if _legibility(t) < _MIN_LEGIBILITY:
        return False
    if _MATH.search(t):
        return False
    return True


def _page_text(page) -> str:
    try:
        return page.get_textpage().get_text_range() or ""
    except Exception:
        return ""


def _has_figure(page) -> bool:
    """True if the page carries visual content the text layer can't represent — a
    raster image of meaningful size or many vector drawings (chart/diagram/ruled
    table). Such a page must go to vision so the figure isn't silently dropped."""
    import pypdfium2.raw as pdfium_c

    try:
        pw, ph = page.get_size()
        page_area = pw * ph
        objs = list(page.get_objects())
    except Exception:
        return False
    if page_area <= 0:
        return False

    img_frac = 0.0
    path_count = 0
    for obj in objs:
        if obj.type == pdfium_c.FPDF_PAGEOBJ_IMAGE:
            try:
                l, b, r, t = obj.get_bounds()  # images expose get_bounds, not get_pos
                img_frac += max(0.0, r - l) * max(0.0, t - b) / page_area
            except Exception:
                img_frac += _MIN_IMG_AREA  # unknown size -> assume significant
        elif obj.type == pdfium_c.FPDF_PAGEOBJ_PATH:
            path_count += 1
    return img_frac >= _MIN_IMG_AREA or path_count >= _MAX_PROSE_PATHS


def _route_to_text(page, text: str) -> bool:
    """A page uses the free text layer only if it's clean prose AND figure-free."""
    return _is_clean_prose(text) and not _has_figure(page)


def render_pages(data: bytes, *, scale: float = 2.0, max_pages: int | None = None):
    """Render PDF pages to PNG bytes (for display / vision). Returns (pngs, total)."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    total = len(pdf)
    count = total if max_pages is None else min(total, max_pages)
    images = []
    for i in range(count):
        buf = BytesIO()
        pdf[i].render(scale=scale).to_pil().save(buf, format="PNG")
        images.append(buf.getvalue())
    return images, total


def parse_pdf(
    data: bytes,
    filename: str,
    *,
    model: str | None = None,
    scale: float = 2.0,
    detail: str = "high",
    max_pages: int | None = None,
    mode: str = "auto",
) -> ParsedDoc:
    """Parse a PDF. mode="auto" routes clean-prose pages to the free text layer and
    only spends a vision call where needed; mode="vision" forces vision on every page.
    """
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(data)
    except Exception as exc:
        raise ParseError(f"Could not open PDF: {exc}") from exc
    total = len(pdf)
    if total == 0:
        raise ParseError("PDF has no pages.")
    count = total if max_pages is None else min(total, max_pages)

    parts: list[str] = []
    routes: list[str] = []
    p_tok = c_tok = 0
    used_model = ""
    for i in range(count):
        page = pdf[i]
        if mode == "auto":
            text = _page_text(page)
            if _route_to_text(page, text):
                parts.append(text.strip())
                routes.append("text")
                continue

        buf = BytesIO()
        page.render(scale=scale).to_pil().save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        try:
            res = llm_client.transcribe_image(b64, PROMPT, model=model, detail=detail)
        except Exception as exc:
            raise ParseError(f"Vision transcription failed: {exc}") from exc
        parts.append((res.text or "").strip())
        routes.append("vision")
        used_model = res.model or used_model
        if res.usage:
            p_tok += res.usage.prompt_tokens
            c_tok += res.usage.completion_tokens

    return ParsedDoc(
        filename=filename,
        pages=count,
        total_pages=total,
        page_markdown=parts,
        markdown="\n\n".join(parts).strip(),
        model=used_model or (model or "—"),
        prompt_tokens=p_tok,
        completion_tokens=c_tok,
        routes=routes,
    )

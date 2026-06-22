"""PDF parsing via Docling — the SOTA representation for the Noema pipeline.

The **canonical artifact is the DoclingDocument**, kept as its lossless dict
(`doc_dict`): it retains structure (headings, tables, reading order) and
**page provenance** that Markdown drops but citations and the HybridChunker (the
next step) need. Markdown is a *derived view* — for display, and later for the
per-chunk text fed to embeddings / the model. You can always go structure ->
Markdown, never the reverse.

Engines (pick per document / corpus; validate on your own files):
  - "standard": layout model + embedded text, no OCR. Fast; clean digital PDFs.
  - "ocr":      standard + forced full-page OCR. Rebuilds the text from pixels —
                for broken-font (LaTeX/ToUnicode) or scanned PDFs.
  - "vlm":      Granite-Docling VLM (MLX on Apple Silicon, else Transformers).
                Reads rendered pages end-to-end into DocTags (tables, equations,
                layout). Reads pixels, so it bypasses broken text layers; SOTA on
                complex / math documents. Heavier (a small VLM per page).
  - "auto":     parse with "standard"; if the text comes out garbled (low
                legibility) escalate to "ocr". The robust default.
"""

from __future__ import annotations

import platform
from dataclasses import dataclass
from io import BytesIO

ENGINES = ("standard", "ocr", "vlm")

# Below this letters/whitespace ratio, an embedded text layer is treated as
# garbled (e.g. a LaTeX PDF with a broken ToUnicode map -> glyph soup).
GARBLED_BELOW = 0.6


class ParseError(ValueError):
    """A document could not be parsed or yielded no extractable content."""


@dataclass(frozen=True)
class ParsedDoc:
    filename: str
    pages: int
    engine: str
    markdown: str  # derived view of doc_dict
    doc_dict: dict  # lossless DoclingDocument — the canonical artifact
    formulas: bool = False  # was formula decoding (image -> LaTeX) active

    @property
    def chars(self) -> int:
        return len(self.markdown)

    @property
    def legibility(self) -> float:
        """Share of letters/whitespace; < GARBLED_BELOW flags a garbled text layer."""
        if not self.markdown:
            return 0.0
        return sum(c.isalpha() or c.isspace() for c in self.markdown) / len(self.markdown)


# One converter per engine, built lazily (each loads its models on first use).
_converters: dict[str, object] = {}


def _apple_silicon() -> bool:
    return platform.system() == "Darwin" and platform.machine() == "arm64"


def _build_converter(engine: str, formulas: bool = False):
    from docling.datamodel.base_models import InputFormat
    from docling.document_converter import DocumentConverter, PdfFormatOption

    if engine == "vlm":
        # The VLM reads pages end-to-end and transcribes formulas natively, so the
        # separate formula model is neither used nor needed here.
        from docling.datamodel import vlm_model_specs
        from docling.datamodel.pipeline_options import VlmPipelineOptions
        from docling.pipeline.vlm_pipeline import VlmPipeline

        spec = (
            vlm_model_specs.GRANITEDOCLING_MLX
            if _apple_silicon()
            else vlm_model_specs.GRANITEDOCLING_TRANSFORMERS
        )
        options = VlmPipelineOptions(vlm_options=spec)
        return DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_cls=VlmPipeline, pipeline_options=options
                )
            }
        )

    from docling.datamodel.pipeline_options import PdfPipelineOptions

    options = PdfPipelineOptions()
    options.do_ocr = engine == "ocr"
    if engine == "ocr":
        # Ignore the (possibly broken) embedded text layer and OCR the pixels.
        options.ocr_options.force_full_page_ocr = True
    if formulas:
        # Transcribe formula images to LaTeX (else they become a
        # <!-- formula-not-decoded --> placeholder). Loads the CodeFormula model.
        options.do_formula_enrichment = True
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )


def _get_converter(engine: str, formulas: bool = False):
    key = (engine, formulas)
    if key not in _converters:
        _converters[key] = _build_converter(engine, formulas)
    return _converters[key]


def parse_pdf(
    data: bytes, filename: str, *, engine: str = "auto", formulas: bool = False
) -> ParsedDoc:
    """Parse a PDF into a ParsedDoc. Raises ParseError on failure.

    engine: "standard" | "ocr" | "vlm" | "auto" (default). "auto" runs the fast
    standard engine and escalates to forced OCR if the text layer is garbled.
    formulas=True decodes formula images to LaTeX (ignored by "vlm", which does
    it natively).
    """
    if engine == "auto":
        doc = _parse_one(data, filename, "standard", formulas)
        if doc.legibility < GARBLED_BELOW:
            doc = _parse_one(data, filename, "ocr", formulas)
        return doc
    if engine not in ENGINES:
        raise ParseError(f"Unknown engine {engine!r}; use one of {ENGINES} or 'auto'.")
    return _parse_one(data, filename, engine, formulas)


def _parse_one(data: bytes, filename: str, engine: str, formulas: bool = False) -> ParsedDoc:
    from docling.datamodel.base_models import DocumentStream

    source = DocumentStream(name=filename, stream=BytesIO(data))
    try:
        result = _get_converter(engine, formulas).convert(source)
    except Exception as exc:  # Docling surfaces various backend-specific errors
        raise ParseError(f"Could not parse document ({engine}): {exc}") from exc

    doc = getattr(result, "document", None)
    if doc is None:
        raise ParseError(f"Could not parse document (no content, engine={engine}).")

    markdown = (doc.export_to_markdown() or "").strip()
    if not markdown:
        raise ParseError(
            "No extractable content found — the document may be empty or unreadable."
        )

    try:
        pages = doc.num_pages()
    except Exception:
        pages = len(getattr(doc, "pages", {}) or {})

    return ParsedDoc(
        filename=filename,
        pages=pages,
        engine=engine,
        markdown=markdown,
        doc_dict=doc.export_to_dict(),
        formulas=formulas and engine != "vlm",
    )

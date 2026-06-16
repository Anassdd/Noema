"""PDF text extraction (text-based PDFs only).

Pulls plain text out of a PDF with pypdf. This is extraction *only* — no
chunking, embedding, or context injection; those come in the RAG slice. There's
no OCR either, so scanned/image-only PDFs yield no text and are rejected with a
clear message rather than returning an empty string.

Per-page text is kept (not just the concatenation) because the eventual
citation feature needs page numbers — the structure is ready for it now.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class PdfError(ValueError):
    """A PDF could not be read, is locked, or has no extractable text."""


@dataclass(frozen=True)
class ExtractedPdf:
    filename: str
    pages: int
    page_texts: list[str]  # one entry per page (may be "" for blank pages)
    text: str  # all pages joined, the usable extraction

    @property
    def chars(self) -> int:
        return len(self.text)


def extract_pdf(data: bytes, filename: str) -> ExtractedPdf:
    """Extract text from PDF bytes. Raises PdfError on anything unreadable."""
    try:
        reader = PdfReader(BytesIO(data))
    except (PdfReadError, OSError, ValueError) as exc:
        raise PdfError(f"Could not read PDF: {exc}") from exc

    # Some PDFs are encrypted but openable with an empty password (owner-locked,
    # still readable). Try that; give up cleanly if it really needs a password.
    if reader.is_encrypted:
        try:
            if reader.decrypt("") == 0:
                raise PdfError("PDF is password-protected.")
        except (NotImplementedError, PdfReadError) as exc:
            raise PdfError(f"PDF is encrypted and could not be opened: {exc}") from exc

    page_texts = [(page.extract_text() or "").strip() for page in reader.pages]
    text = "\n\n".join(t for t in page_texts if t).strip()

    if not text:
        raise PdfError(
            "No extractable text found — this looks like a scanned or image-only "
            "PDF, which isn't supported (no OCR)."
        )

    return ExtractedPdf(
        filename=filename,
        pages=len(reader.pages),
        page_texts=page_texts,
        text=text,
    )

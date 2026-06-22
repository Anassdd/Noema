"""Azure Document Intelligence parser — the deterministic backbone (prod track).

Sends the PDF to Azure DI's `prebuilt-layout` model and returns Markdown (tables as
HTML) + formulas as LaTeX, with page-level provenance. Deterministic — it doesn't
hallucinate — and fully in-tenant. The research's recommended backbone for grounded,
citation-grade RAG (vision is the fallback for hard pages).

Selected by `PARSER=docintel` in `.env`; needs `DOCINTEL_ENDPOINT` + `DOCINTEL_KEY`.

STATUS: wired and import-verified against the GA SDK (1.0.x), but NOT yet run against
a live DI resource (none on the dev Mac). Validate on the company's Azure DI before
relying on it — the call shape is correct per the SDK but only a real endpoint proves it.
"""

from __future__ import annotations

from app.config import settings
from app.parsing.base import ParsedDoc, ParseError


def parse(data: bytes, filename: str) -> ParsedDoc:
    if not settings.docintel_endpoint or not settings.docintel_key:
        raise ParseError(
            "Document Intelligence not configured — set DOCINTEL_ENDPOINT and "
            "DOCINTEL_KEY (and PARSER=docintel)."
        )
    try:
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.ai.documentintelligence.models import (
            AnalyzeDocumentRequest,
            DocumentAnalysisFeature,
            DocumentContentFormat,
        )
        from azure.core.credentials import AzureKeyCredential
    except Exception as exc:  # pragma: no cover
        raise ParseError(f"azure-ai-documentintelligence not installed: {exc}") from exc

    client = DocumentIntelligenceClient(
        settings.docintel_endpoint, AzureKeyCredential(settings.docintel_key)
    )
    try:
        poller = client.begin_analyze_document(
            "prebuilt-layout",
            AnalyzeDocumentRequest(bytes_source=data),
            features=[DocumentAnalysisFeature.FORMULAS],  # equations -> LaTeX (paid add-on)
            output_content_format=DocumentContentFormat.MARKDOWN,
        )
        result = poller.result()
    except Exception as exc:
        raise ParseError(f"Document Intelligence request failed: {exc}") from exc

    markdown = (result.content or "").strip()
    if not markdown:
        raise ParseError("Document Intelligence returned no content.")
    pages = len(result.pages or []) or 1
    return ParsedDoc(
        filename=filename,
        pages=pages,
        total_pages=pages,
        page_markdown=[markdown],  # DI returns unified Markdown; provenance is per-element in result
        markdown=markdown,
        model="azure-document-intelligence",
        routes=["docintel"],
    )

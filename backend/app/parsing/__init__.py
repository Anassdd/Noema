"""PDF parsing package. See PARSING.md for how it works and its trade-offs.

Public API (this is all the rest of the app should use):
    parse_document(data, filename) -> ParsedDoc   # routes by the PARSER env var
    ParsedDoc, ParseError                          # the shared return type + error

Backends are selected by PARSER in .env, never by the caller:
    vision   — render page -> vision LLM (default; works on dev + Azure)
    docintel — Azure Document Intelligence (deterministic; awaiting a live resource)
"""

from app.parsing.base import ParsedDoc, ParseError
from app.parsing.dispatch import parse_document

__all__ = ["parse_document", "ParsedDoc", "ParseError"]

"""Parser seam — pick the backend by config (mirrors the LLM provider).

  PARSER=vision   (default) → render pages → vision LLM (works wherever the LLM does)
  PARSER=docintel           → Azure Document Intelligence (deterministic, in-tenant)

Both return a `ParsedDoc`, so callers don't care which ran. Switching dev (vision via
OpenAI) → prod (DI / vision via Azure) is a `.env` change, no code change.
"""

from __future__ import annotations

from app.config import settings
from app.parsing import vision
from app.parsing.base import ParsedDoc


def parse_document(data: bytes, filename: str, *, model: str | None = None) -> ParsedDoc:
    if settings.parser == "docintel":
        from app.parsing import docintel  # lazy — only import the SDK path when chosen

        return docintel.parse(data, filename)  # DI is model-free; `model` applies to vision only
    return vision.parse_pdf(data, filename, model=model)

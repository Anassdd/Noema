"""Chunking package — turn parsed Markdown into provenance-tagged retrieval chunks.

See CHUNKING.md for how it works and why.

Public API:
    chunk_parsed_doc(parsed_doc) -> list[Chunk]   # page provenance from per-page Markdown
    chunk_markdown(markdown)     -> list[Chunk]   # raw Markdown, no page info
    Chunk                                          # the provenance-tagged passage type
"""

from app.chunking.base import Chunk
from app.chunking.markdown_chunker import chunk_markdown, chunk_parsed_doc

__all__ = ["Chunk", "chunk_markdown", "chunk_parsed_doc"]

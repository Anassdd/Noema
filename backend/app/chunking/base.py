"""Shared chunking types — the `Chunk` the chunker produces and retrieval consumes.

A chunk is a retrievable passage plus the provenance needed to cite it (doc + page
+ section) and to rebuild context. Kept apart from the algorithm so callers depend on
the type, not the implementation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    index: int
    text: str
    header_path: list[str] = field(default_factory=list)  # ["Methods", "Data"]
    pages: list[int] = field(default_factory=list)  # source page numbers (provenance)
    token_count: int = 0
    char_count: int = 0
    overlap_tokens: int = 0  # leading tokens carried over from the previous chunk
    domain_id: str = "default"

    @property
    def section(self) -> str:
        return " › ".join(self.header_path)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["section"] = self.section
        return d

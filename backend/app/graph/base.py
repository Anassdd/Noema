"""Graph-layer types — the small, serializable shapes the lab/tests read.

These deliberately flatten Graphiti's rich nodes/edges into plain dataclasses with
ISO-string timestamps so a snapshot round-trips cleanly to JSON (kept edge-case
results) and renders without a live graph connection.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime


def iso(dt) -> str | None:
    return dt.isoformat() if isinstance(dt, datetime) else dt


@dataclass
class GraphFact:
    """A retrieved fact (an EntityEdge) with its temporal validity, ready to cite."""

    uuid: str
    fact: str
    source: str = "?"          # source entity name
    target: str = "?"          # target entity name
    name: str = ""             # relationship type
    valid_at: str | None = None      # when true in the world
    invalid_at: str | None = None    # when it stopped being true (None = still true)
    created_at: str | None = None    # when Graphiti learned it
    expired_at: str | None = None    # when Graphiti superseded it
    episodes: list[str] = field(default_factory=list)  # source episode uuids (provenance)
    score: float | None = None

    @property
    def is_current(self) -> bool:
        return self.invalid_at is None and self.expired_at is None

    def to_dict(self) -> dict:
        return {**asdict(self), "is_current": self.is_current}


@dataclass
class GraphNode:
    uuid: str
    name: str
    labels: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GraphEdge:
    uuid: str
    source_uuid: str
    target_uuid: str
    name: str = ""
    fact: str = ""
    valid_at: str | None = None
    invalid_at: str | None = None
    expired_at: str | None = None
    created_at: str | None = None  # when Graphiti learned this fact (ingestion time)

    @property
    def is_current(self) -> bool:
        return self.invalid_at is None and self.expired_at is None

    def to_dict(self) -> dict:
        return {**asdict(self), "is_current": self.is_current}


@dataclass
class GraphSnapshot:
    """The whole graph for a domain — every node and edge, including invalidated
    ones (so the temporal history is visible, not hidden)."""

    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"nodes": [n.to_dict() for n in self.nodes],
                "edges": [e.to_dict() for e in self.edges]}

    @classmethod
    def from_dict(cls, d: dict) -> "GraphSnapshot":
        nf = GraphNode.__dataclass_fields__
        ef = GraphEdge.__dataclass_fields__
        return cls(
            nodes=[GraphNode(**{k: v for k, v in n.items() if k in nf}) for n in d.get("nodes", [])],
            edges=[GraphEdge(**{k: v for k, v in e.items() if k in ef}) for e in d.get("edges", [])],
        )

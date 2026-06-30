"""Graph memory package — a temporal knowledge graph (Graphiti) as a pluggable,
backend-swappable memory, kept separate from the contextual vector base.

Lives in the unified backend venv (Python 3.12 — graphiti-core needs it, and the whole
project now targets 3.12 so the contextual base and the graph share one process).
Standalone for now; a thin adapter to the retrieval `ScoredChunk` seam connects it to
the chatbot later.

Public API:
    GraphMemory(domain_id)             build / add_episode / search / snapshot / reset
    GraphFact, GraphNode, GraphEdge, GraphSnapshot
    render_html(snapshot)              self-contained interactive SVG of the graph
    graph_config                       backend selection (embedded now, server later)
"""

from app.graph.base import GraphEdge, GraphFact, GraphNode, GraphSnapshot
from app.graph.config import GraphConfig, graph_config, load_graph_config
from app.graph.store import GraphMemory
from app.graph.viz import render_html

__all__ = [
    "GraphMemory", "GraphFact", "GraphNode", "GraphEdge", "GraphSnapshot",
    "render_html", "graph_config", "GraphConfig", "load_graph_config",
]

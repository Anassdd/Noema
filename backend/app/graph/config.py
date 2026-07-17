"""Graph-layer configuration — backend selection, isolated from the LLM provider.

The graph store backend is swappable WITHOUT touching graph logic, chosen by
`GRAPH_BACKEND` in .env:
  - "falkor_local"    : the DEFAULT — auto-runs the FalkorDB server bundled inside
                        falkordblite as one shared local process (no Docker, no
                        install). Reliable under graphiti's concurrent writes.
  - "falkor_embedded" : pure in-process redislite, no separate process. Lightest, but
                        flaky under graphiti's concurrent writes in this version.
  - "falkor_server"   : an external FalkorDB server (host/port) — drop-in for later.
  - "neo4j"           : a Neo4j server (uri/user/password).

LLM/embedder credentials are deliberately NOT duplicated here — they come from
app.config.settings (the single provider-abstraction source), so OpenAI↔Azure stays
one .env switch for the graph exactly as it is for the rest of the app.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_REPO = Path(__file__).resolve().parents[3]
load_dotenv(_REPO / "backend" / ".env")

from app.config import state_path

_DEFAULT_STORE = state_path("falkor", _REPO / "tests" / "results" / "graph_store")


@dataclass(frozen=True)
class GraphConfig:
    backend: str = "falkor_local"             # falkor_local | falkor_embedded | falkor_server | neo4j
    db_dir: str = str(_DEFAULT_STORE)         # where the .rdb persistence lives
    host: str = "127.0.0.1"                    # falkor_local / falkor_server
    port: int = 6399                           # 6399 to avoid clashing with a system redis on 6379
    username: str = ""
    password: str = ""
    neo4j_uri: str = "bolt://localhost:7687"   # neo4j
    extract_model: str = ""                    # blank -> resolved from settings in providers
    # Graph search recipe: "rrf" (Graphiti's basic hybrid — the measured baseline),
    # "cross_encoder" (LLM-reranked facts, ~graph_limit extra cheap calls per query),
    # or "mmr". Part of run provenance — don't mix recipes within one comparison.
    search_recipe: str = "rrf"
    # Cap on Graphiti's internal concurrent LLM calls during ingestion.
    # 0 = library default (~20); lower it on rate-limited keys or gateways.
    max_coroutines: int = 0


def load_graph_config() -> GraphConfig:
    return GraphConfig(
        backend=os.getenv("GRAPH_BACKEND", "falkor_local").strip().lower(),
        db_dir=os.getenv("GRAPH_DB_DIR", str(_DEFAULT_STORE)),
        host=os.getenv("FALKOR_HOST", "127.0.0.1"),
        port=int(os.getenv("FALKOR_PORT", "6399")),
        username=os.getenv("FALKOR_USER", ""),
        password=os.getenv("FALKOR_PASSWORD", ""),
        neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        extract_model=os.getenv("GRAPH_EXTRACT_MODEL", ""),
        search_recipe=os.getenv("GRAPH_SEARCH_RECIPE", "rrf").strip().lower(),
        max_coroutines=int(os.getenv("GRAPH_MAX_COROUTINES", "0") or 0),
    )


graph_config = load_graph_config()

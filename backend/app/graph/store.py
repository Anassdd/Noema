"""GraphMemory — a temporal knowledge-graph memory over Graphiti, one graph per domain.

This is the whole graph layer behind a small, stable surface: build, add_episode,
search, snapshot, reset. The Graphiti backend is chosen by GraphConfig (embedded
FalkorDB Lite now, a FalkorDB/Neo4j server later) — swapping it touches nothing here.

All public methods are async (Graphiti is async). Sync call sites — the lab, the test
runner — use the module's `run_on(loop, coro)` / `GraphMemory.run(coro)` helpers.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from graphiti_core import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.edges import EntityEdge
from graphiti_core.nodes import EntityNode, EpisodeType
from graphiti_core.utils.maintenance.graph_data_operations import clear_data

from app.graph.base import GraphEdge, GraphFact, GraphNode, GraphSnapshot, iso
from app.graph.config import GraphConfig, graph_config
from app.graph.providers import build_cross_encoder, build_embedder, build_llm_client
from app.graph.schema import InducedSchema, load_schema, schema_instructions
from app.saves import base_group_id


# Graphiti's default extraction is tuned for formal named entities and yields nothing
# on short/informal/opinion text ("anas likes pizza more than burger" → empty graph).
# This instruction broadens it to everyday entities + preferences while keeping the
# person/subject as a node. Overridable per-memory or per-episode.
DEFAULT_EXTRACTION_INSTRUCTIONS = (
    "Extract every meaningful entity mentioned — including people, organizations, places, "
    "products, brands, foods, works, and everyday concepts (even common nouns like 'pizza') "
    "— and the relationships, preferences, opinions, comparisons and attributes that connect "
    "them. Always include the person or subject who holds an opinion or preference as an "
    "entity, linked to the things they prefer or reject."
)

# Corpus ingestion (PDF pages, bench documents) extracts with this instead: expository
# text has no speaker holding preferences — its value is domain concepts and the
# assertions connecting them. The chat-memory default above would litter a filing's
# graph with everyday nouns.
DOCUMENT_EXTRACTION_INSTRUCTIONS = (
    "This text is from a reference document (a paper, regulation, filing, manual or "
    "article), not a conversation. Extract what a domain expert would index: domain "
    "concepts and defined terms, organizations and institutions, standards and "
    "regulations with their identifiers, named methods, models, products and financial "
    "instruments, metrics and quantities with their values, and people in their "
    "professional roles. Use the canonical name the document itself uses; resolve "
    "pronouns and abbreviations to their referents. Capture the relationships the text "
    "asserts — definitions, requirements and obligations, applicability and scope, "
    "causal and quantitative links, comparisons, part-whole and supersession — as "
    "specific directional facts. Do not extract conversational filler, generic everyday "
    "nouns, or document-structure words (section, table, figure, page)."
)


def _build_driver(cfg: GraphConfig, domain_id: str):
    # FalkorDB stores each group in a graph named after it, so the driver's `database`
    # must equal the domain_id — otherwise reads (get_by_group_ids) hit the wrong graph.
    if cfg.backend == "falkor_local":
        # One shared local FalkorDB process (bundled binary); each domain is its own
        # graph within it.
        from app.graph.server import ensure_local_server
        host, port = ensure_local_server(cfg.host, cfg.port, str(Path(cfg.db_dir) / "server"))
        return FalkorDriver(host=host, port=port, database=domain_id)
    if cfg.backend == "falkor_embedded":
        from redislite import AsyncFalkorDB
        Path(cfg.db_dir).mkdir(parents=True, exist_ok=True)
        db = AsyncFalkorDB(dbfilename=str(Path(cfg.db_dir) / f"{domain_id}.rdb"))
        return FalkorDriver(falkor_db=db, database=domain_id)
    if cfg.backend == "falkor_server":
        return FalkorDriver(host=cfg.host, port=cfg.port, database=domain_id,
                            username=cfg.username or None, password=cfg.password or None)
    if cfg.backend == "neo4j":
        from graphiti_core.driver.neo4j_driver import Neo4jDriver
        return Neo4jDriver(uri=cfg.neo4j_uri, user=cfg.username or "neo4j", password=cfg.password)
    raise ValueError(f"Unknown GRAPH_BACKEND={cfg.backend!r} "
                     "(expected falkor_local | falkor_embedded | falkor_server | neo4j)")


class GraphMemory:
    """One temporal graph for one domain. Construct, then `await build()` once."""

    def __init__(self, domain_id: str = "default", *, config: GraphConfig | None = None,
                 extract_model: str | None = None, extraction_instructions: str | None = None,
                 schema: InducedSchema | None = None, use_saved_schema: bool = True):
        self.domain_id = domain_id  # the graph/database to CONNECT to
        # the group_id the data carries — differs from domain_id only for save snapshots,
        # whose graph is a raw copy that keeps the base domain's group_id.
        self.group_id = base_group_id(domain_id)
        self.config = config or graph_config
        self._base_instructions = extraction_instructions or DEFAULT_EXTRACTION_INSTRUCTIONS
        self.schema = schema if schema is not None else (load_schema(domain_id) if use_saved_schema else None)
        self.extraction_instructions = self._resolve_instructions()
        self._driver = _build_driver(self.config, domain_id)
        # Graphiti reroutes WRITES to a database named after the group_id (its
        # multi-tenant convenience, via driver.clone). For a save-key domain —
        # writing INTO a checkpoint, e.g. a bench build — that would silently
        # write into the LIVE base graph instead. Pin the driver to this graph.
        if self.domain_id != self.group_id:
            self._driver.clone = lambda database: self._driver
        self.graphiti = Graphiti(
            graph_driver=self._driver,
            llm_client=build_llm_client(extract_model or self.config.extract_model or None),
            embedder=build_embedder(),
            cross_encoder=build_cross_encoder(),
            max_coroutines=self.config.max_coroutines or None,
        )

    def instructions_for(self, kind: str = "memory") -> str:
        """Extraction instructions for one episode: the induced-schema prefix (when the
        domain has one) + the base suited to the text — "document" for corpus/PDF
        ingestion, "memory" for conversational or pasted notes. A raw per-episode
        override would silently drop the schema prefix; this keeps it."""
        base = DOCUMENT_EXTRACTION_INSTRUCTIONS if kind == "document" else self._base_instructions
        si = schema_instructions(self.schema) if self.schema else ""
        return f"{si} {base}".strip() if si else base

    def _resolve_instructions(self) -> str:
        return self.instructions_for("memory")

    def apply_schema(self, schema: InducedSchema | None):
        """Bound future extraction to an induced domain schema (or clear it)."""
        self.schema = schema
        self.extraction_instructions = self._resolve_instructions()

    # ---- ingestion --------------------------------------------------------
    async def build(self) -> "GraphMemory":
        await self.graphiti.build_indices_and_constraints()
        return self

    async def all_episode_names(self) -> set[str]:
        """Every episode name in this domain — lets an interrupted bulk ingestion
        resume by skipping pieces that already made it in."""
        records, _, _ = await self._driver.execute_query(
            "MATCH (e:Episodic) WHERE e.group_id = $g RETURN e.name AS name",
            g=self.group_id)
        return {r["name"] for r in records or []}

    async def graph_health(self) -> dict:
        """Cheap quality indicators for reports: orphan entities (no facts), archived
        facts, episode count, and name-collision suspects (same normalized name twice —
        the dedupe pass's raw material)."""
        async def _count(cypher: str) -> int:
            records, _, _ = await self._driver.execute_query(cypher, g=self.group_id)
            return int(records[0]["n"]) if records else 0

        orphans = await _count(
            "MATCH (x:Entity) WHERE x.group_id = $g AND NOT (x)-[:RELATES_TO]-() "
            "RETURN count(x) AS n")
        episodes = await _count(
            "MATCH (e:Episodic) WHERE e.group_id = $g RETURN count(e) AS n")
        archived = await _count(
            "MATCH ()-[r:RELATES_TO]->() WHERE r.group_id = $g AND r.archived = true "
            "RETURN count(r) AS n")
        records, _, _ = await self._driver.execute_query(
            "MATCH (x:Entity) WHERE x.group_id = $g RETURN x.name AS name", g=self.group_id)
        names = [" ".join(str(r["name"]).lower().split()) for r in records or []]
        duplicates = len(names) - len(set(names))
        return {"orphans": orphans, "episodes": episodes, "archived_facts": archived,
                "duplicate_name_suspects": duplicates}

    async def add_episode(self, body: str, *, name: str | None = None,
                          source_description: str = "user input",
                          reference_time: datetime | None = None,
                          update_communities: bool = False,
                          extraction_instructions: str | None = None):
        """Fold one piece of text into the graph: extract → resolve → relate →
        invalidate contradictions. Incremental — never rebuilds the graph."""
        ref = reference_time or datetime.now(timezone.utc)
        return await self.graphiti.add_episode(
            name=name or f"ep-{ref.isoformat()}",
            episode_body=body,
            source=EpisodeType.text,
            source_description=source_description,
            reference_time=ref,
            group_id=self.group_id,
            update_communities=update_communities,
            custom_extraction_instructions=extraction_instructions or self.extraction_instructions,
        )

    # ---- retrieval --------------------------------------------------------
    async def search(self, query: str, limit: int = 10) -> list[GraphFact]:
        """Top `limit` LIVE facts: archived ones are known up front and the fetch is
        widened by their count, so they never eat result slots."""
        archived = await self._archived_uuids()
        fetch = min(limit + len(archived), limit * 3) if archived else limit
        edges = await self._search_edges(query, fetch)
        live = [e for e in edges if e.uuid not in archived][:limit]
        names = await self._node_names()
        return [self._to_fact(e, names) for e in live]

    async def _search_edges(self, query: str, limit: int):
        """The one place the search recipe is chosen. "rrf" keeps Graphiti's basic
        hybrid search — the measured baseline; richer recipes go through search_() on
        a COPY (the module-level recipes are shared singletons, never mutate them)."""
        recipe = (self.config.search_recipe or "rrf").lower()
        if recipe == "rrf":
            return await self.graphiti.search(query, group_ids=[self.group_id],
                                              num_results=limit)
        from graphiti_core.search.search_config_recipes import (
            EDGE_HYBRID_SEARCH_CROSS_ENCODER, EDGE_HYBRID_SEARCH_MMR)
        recipes = {"cross_encoder": EDGE_HYBRID_SEARCH_CROSS_ENCODER,
                   "mmr": EDGE_HYBRID_SEARCH_MMR}
        if recipe not in recipes:
            raise ValueError(f"Unknown GRAPH_SEARCH_RECIPE={recipe!r} "
                             "(expected rrf | cross_encoder | mmr)")
        config = recipes[recipe].model_copy(deep=True)
        config.limit = limit
        results = await self.graphiti.search_(query, config=config,
                                              group_ids=[self.group_id])
        return results.edges

    async def _edge_count(self) -> int:
        """Raw fact-edge count straight from Cypher — independent of edge parsing."""
        try:
            res = await self._driver.execute_query(
                "MATCH ()-[r:RELATES_TO]->() WHERE r.group_id = $g RETURN count(r) AS n",
                g=self.group_id,
            )
            records = res[0] if isinstance(res, tuple) else res
            return records[0]["n"] if records else 0
        except Exception:
            return 0

    async def _archived_uuids(self) -> set[str]:
        """Facts Dream demoted out of active retrieval (still in snapshots/history)."""
        try:
            res = await self._driver.execute_query(
                "MATCH ()-[r:RELATES_TO]->() WHERE r.group_id = $g AND r.archived = true "
                "RETURN r.uuid AS uuid",
                g=self.group_id,
            )
            records = res[0] if isinstance(res, tuple) else res
            return {row["uuid"] for row in (records or [])}
        except Exception:
            return set()

    async def top_entities(self, limit: int = 15) -> list[str]:
        """The most connected entity names — a one-line map of what this graph knows,
        fed to the chat router so it can tell same-document from cross-document questions."""
        try:
            records, _, _ = await self._driver.execute_query(
                "MATCH (x:Entity) WHERE x.group_id = $g "
                "OPTIONAL MATCH (x)-[r:RELATES_TO]-() "
                "RETURN x.name AS name, count(r) AS degree "
                f"ORDER BY degree DESC LIMIT {int(limit)}",
                g=self.group_id)
            return [r["name"] for r in records or [] if r["name"]]
        except Exception:
            return []

    async def episode_names(self, uuids: list[str]) -> dict[str, str]:
        """Resolve episode UUIDs → their names (we name episodes '<file> · p<N>'), so a
        retrieved fact can cite the document + page it came from. Best-effort."""
        uuids = list({u for u in uuids if u})
        if not uuids:
            return {}
        try:
            from graphiti_core.nodes import EpisodicNode
            eps = await EpisodicNode.get_by_uuids(self._driver, uuids)
            return {e.uuid: (e.name or "") for e in eps}
        except Exception:
            return {}

    async def snapshot(self) -> GraphSnapshot:
        """The full current graph for this domain — all nodes and all edges,
        including invalidated ones, so the temporal history stays visible."""
        nodes = await self._nodes()
        try:
            edges = await EntityEdge.get_by_group_ids(self._driver, [self.group_id])
        except Exception:
            # Only an edgeless graph may read as empty — a parse failure on a graph
            # that HAS edges must surface, or callers would mistake it for "no facts".
            if await self._edge_count() > 0:
                raise
            edges = []
        gn = [GraphNode(uuid=n.uuid, name=n.name, labels=list(n.labels or []),
                        summary=n.summary or "") for n in nodes]
        ge = [GraphEdge(uuid=e.uuid, source_uuid=e.source_node_uuid,
                        target_uuid=e.target_node_uuid, name=e.name or "", fact=e.fact or "",
                        valid_at=iso(e.valid_at), invalid_at=iso(e.invalid_at),
                        expired_at=iso(e.expired_at), created_at=iso(e.created_at)) for e in edges]
        return GraphSnapshot(nodes=gn, edges=ge)

    # ---- maintenance ------------------------------------------------------
    async def reset(self):
        await clear_data(self._driver, group_ids=[self.group_id])

    async def close(self):
        try:
            await self.graphiti.close()
        except Exception:
            pass

    # ---- internals --------------------------------------------------------
    async def _nodes(self):
        try:
            return await EntityNode.get_by_group_ids(self._driver, [self.group_id])
        except Exception:
            return []

    async def _node_names(self) -> dict[str, str]:
        return {n.uuid: n.name for n in await self._nodes()}

    def _to_fact(self, e, names) -> GraphFact:
        return GraphFact(
            uuid=e.uuid, fact=e.fact or "", name=e.name or "",
            source=names.get(e.source_node_uuid, "?"),
            target=names.get(e.target_node_uuid, "?"),
            valid_at=iso(e.valid_at), invalid_at=iso(e.invalid_at),
            created_at=iso(e.created_at), expired_at=iso(e.expired_at),
            episodes=list(e.episodes or []),
            score=getattr(e, "score", None),
        )

    @staticmethod
    def run(coro):
        """One-shot sync runner (fresh event loop). Fine for scripts/tests; the
        Streamlit lab uses a single persistent loop instead (see graph_lab.py)."""
        return asyncio.run(coro)

// Pure graphology helpers for the co-occurrence network: keep the live graph in
// sync with the backend snapshot, then color by community (Louvain) and size by
// betweenness (bridges grow) — the InfraNodus recipe. ForceAtlas2 does the layout.
import forceAtlas2 from "graphology-layout-forceatlas2";
import louvain from "graphology-communities-louvain";
import betweenness from "graphology-metrics/centrality/betweenness";

// Vivid, well-separated cluster colors on a dark canvas.
export const PALETTE = [
  "#ff5c8a", "#5cc8ff", "#ffd166", "#9b8cff", "#06d6a0", "#ff8f57",
  "#4ad6c4", "#f487e0", "#7bd64a", "#ff6b6b", "#62b6ff", "#ffd84a",
];

const key = (s, t) => (s < t ? `${s}\t${t}` : `${t}\t${s}`);
const edgeSize = (w) => Math.max(0.35, Math.min(3, w));

// Make the live graph equal the snapshot while preserving surviving nodes'
// positions, so new ingests *grow* the graph instead of relaying it from scratch.
export function reconcile(graph, snapshot) {
  const want = new Set(snapshot.nodes.map((n) => n.id));
  graph.forEachNode((id) => {
    if (!want.has(id)) graph.dropNode(id);
  });

  let added = 0;
  for (const n of snapshot.nodes) {
    if (graph.hasNode(n.id)) {
      graph.setNodeAttribute(n.id, "count", n.count);
    } else {
      graph.addNode(n.id, {
        label: n.label ?? n.id,
        count: n.count,
        x: (Math.random() - 0.5) * 6,
        y: (Math.random() - 0.5) * 6,
        size: 3,
        color: "#8895b3",
      });
      added += 1;
    }
  }

  const wantEdges = new Set(snapshot.edges.map((e) => key(e.source, e.target)));
  graph.forEachEdge((edge, _attr, s, t) => {
    if (!wantEdges.has(key(s, t))) graph.dropEdge(edge);
  });
  for (const e of snapshot.edges) {
    if (!graph.hasNode(e.source) || !graph.hasNode(e.target)) continue;
    if (graph.hasEdge(e.source, e.target)) {
      const ek = graph.edge(e.source, e.target);
      graph.setEdgeAttribute(ek, "weight", e.weight);
      graph.setEdgeAttribute(ek, "size", edgeSize(e.weight));
    } else {
      graph.addEdge(e.source, e.target, { weight: e.weight, size: edgeSize(e.weight) });
    }
  }
  return added;
}

export function applyMetrics(graph) {
  if (graph.order === 0) return;

  try {
    if (graph.size > 0) louvain.assign(graph, { resolution: 1 });
  } catch {
    /* keep previous communities on failure */
  }
  graph.forEachNode((id, attr) => {
    graph.setNodeAttribute(id, "color", PALETTE[(attr.community ?? 0) % PALETTE.length]);
  });

  let bc = {};
  try {
    bc = betweenness(graph, { normalized: true });
  } catch {
    bc = {};
  }
  let max = 0;
  for (const id in bc) max = Math.max(max, bc[id]);
  graph.forEachNode((id) => {
    const b = max > 0 ? (bc[id] ?? 0) / max : 0;
    const deg = Math.min(graph.degree(id), 8);
    graph.setNodeAttribute(id, "size", 4 + 18 * Math.sqrt(b) + deg * 0.35);
  });
}

export function layoutSettings(graph) {
  return {
    ...forceAtlas2.inferSettings(graph),
    linLogMode: true,
    outboundAttractionDistribution: true,
    gravity: 1.1,
    scalingRatio: 9,
    slowDown: 6,
    barnesHutOptimize: graph.order > 300,
  };
}

// One-shot settle for the freshly loaded graph so it opens already laid out.
export function preSettle(graph) {
  if (graph.order === 0) return;
  forceAtlas2.assign(graph, { iterations: 240, settings: layoutSettings(graph) });
}

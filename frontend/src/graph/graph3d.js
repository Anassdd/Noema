// Color/size the Graphiti entities for the 3D view: Louvain communities → color,
// degree → node size. Mutates the node objects in place so 3d-force-graph keeps
// their positions across updates (the graph grows, it doesn't re-lay-out).
import Graph from "graphology";
import louvain from "graphology-communities-louvain";

export const PALETTE = [
  "#5cc8ff", "#ff5c8a", "#ffd166", "#9b8cff", "#06d6a0", "#ff8f57",
  "#4ad6c4", "#f487e0", "#7bd64a", "#ff6b6b", "#62b6ff", "#ffd84a",
];

export function enrich(nodes, links) {
  const g = new Graph({ type: "undirected", multi: true });
  for (const n of nodes) g.addNode(n.id);
  for (const l of links) {
    const s = typeof l.source === "object" ? l.source.id : l.source;
    const t = typeof l.target === "object" ? l.target.id : l.target;
    if (g.hasNode(s) && g.hasNode(t)) g.addEdge(s, t);
  }

  let communities = {};
  try {
    if (g.size > 0) communities = louvain(g);
  } catch {
    communities = {};
  }

  for (const n of nodes) {
    const deg = g.hasNode(n.id) ? g.degree(n.id) : 0;
    n.community = communities[n.id] ?? 0;
    n.color = PALETTE[n.community % PALETTE.length];
    n.val = 1 + deg; // size by connections (hub entities stand out)
  }
  return nodes;
}

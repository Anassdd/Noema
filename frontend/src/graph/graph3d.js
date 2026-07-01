// Color/size the Graphiti entities for the 3D view: Louvain communities → color,
// degree → node size. Mutates the node objects in place so 3d-force-graph keeps
// their positions across updates (the graph grows, it doesn't re-lay-out).
import Graph from "graphology";
import louvain from "graphology-communities-louvain";

export const PALETTE = [
  "#5cc8ff", "#ff5c8a", "#ffd166", "#9b8cff", "#06d6a0", "#ff8f57",
  "#4ad6c4", "#f487e0", "#7bd64a", "#ff6b6b", "#62b6ff", "#ffd84a",
];

// Collapse the graph into one "topic" node per Louvain community (like InfraNodus's
// Topics view). Topic size = cluster size; topic edges aggregate cross-cluster links.
export function topicsFrom(nodes, links) {
  const commOf = {};
  const byComm = {};
  for (const n of nodes) {
    const c = n.community ?? 0;
    commOf[n.id] = c;
    (byComm[c] ??= []).push(n);
  }
  const topicNodes = Object.entries(byComm).map(([comm, members]) => {
    const top = members.reduce((a, b) => ((b.val || 0) > (a.val || 0) ? b : a), members[0]);
    const names = members.map((m) => m.name).sort((a, b) => a.localeCompare(b));
    return {
      id: `topic-${comm}`,
      name: top.name,
      community: +comm,
      color: PALETTE[+comm % PALETTE.length],
      __isTopic: true,
      val: 1 + members.length, // size by cluster size
      members: names,
      summary: `${members.length} entit${members.length === 1 ? "y" : "ies"}: ${names.join(", ")}`,
    };
  });
  const edgeW = {};
  for (const l of links) {
    const s = typeof l.source === "object" ? l.source.id : l.source;
    const t = typeof l.target === "object" ? l.target.id : l.target;
    const cs = commOf[s];
    const ct = commOf[t];
    if (cs == null || ct == null || cs === ct) continue;
    const key = cs < ct ? `${cs}|${ct}` : `${ct}|${cs}`;
    edgeW[key] = (edgeW[key] || 0) + 1;
  }
  const topicLinks = Object.entries(edgeW).map(([key, w]) => {
    const [a, b] = key.split("|");
    return {
      source: `topic-${a}`,
      target: `topic-${b}`,
      weight: w,
      is_current: true,
      __topic: true,
      color: PALETTE[+a % PALETTE.length], // colour the edge by its source cluster
    };
  });
  return { nodes: topicNodes, links: topicLinks };
}

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

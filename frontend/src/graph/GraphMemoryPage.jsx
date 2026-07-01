import { useEffect, useRef, useState } from "react";
import ForceGraph3D from "3d-force-graph";
import SpriteText from "three-spritetext";
import * as THREE from "three";
import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";

import {
  getGraph,
  ingestText,
  uploadPdfStream,
  resetGraph,
  listSaves,
  saveGraph,
  restoreGraph,
  deleteSave,
} from "../api/graphmem.js";
import { fetchModels } from "../api/models.js";
import { enrich, topicsFrom } from "./graph3d.js";

// A flat, camera-facing disk (like the InfraNodus video) — a white circle with a soft
// rim, tinted per node. Built once and shared; SpriteMaterial.color does the tinting.
let _diskTexture = null;
function diskTexture() {
  if (_diskTexture) return _diskTexture;
  const size = 128;
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const ctx = c.getContext("2d");
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  // Solid fill almost to the edge, then a thin anti-aliased rim — a crisp flat circle
  // (like the InfraNodus video), not a soft glowing blob.
  g.addColorStop(0, "rgba(255,255,255,1)");
  g.addColorStop(0.95, "rgba(255,255,255,1)");
  g.addColorStop(1, "rgba(255,255,255,0)"); // solid to the rim, thin anti-alias edge
  ctx.fillStyle = g;
  ctx.beginPath();
  ctx.arc(size / 2, size / 2, size / 2, 0, 2 * Math.PI);
  ctx.fill();
  _diskTexture = new THREE.CanvasTexture(c);
  return _diskTexture;
}

// A standalone tab (?view=graph) showing the REAL memory — Graphiti's entities and
// temporal facts — in 3D. Drop a PDF: each page is extracted by the LLM and the graph
// grows live (streamed per page). The graph persists in FalkorDB, so it's here next time.
export default function GraphMemoryPage() {
  const containerRef = useRef(null);
  const fgRef = useRef(null);
  const nodesRef = useRef(new Map()); // id -> node object (reused so positions persist)

  const [stats, setStats] = useState(null);
  const [status, setStatus] = useState("Loading memory…");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [text, setText] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [models, setModels] = useState([]);
  const [model, setModel] = useState(""); // "" = backend's strong default (gpt-4o)
  const [showHistory, setShowHistory] = useState(true);
  const [selection, setSelection] = useState(null); // clicked node's group inspector
  const [hoveredFact, setHoveredFact] = useState(null); // edge description shown on hover
  const [hoveredNode, setHoveredNode] = useState(null); // node info shown on hover
  const [confirmReset, setConfirmReset] = useState(false);
  const [savesOpen, setSavesOpen] = useState(false);
  const [saves, setSaves] = useState([]);
  const [saveName, setSaveName] = useState("");
  const [viewMode, setViewMode] = useState("concepts"); // "concepts" | "topics"

  const viewModeRef = useRef("concepts");
  const renderedNodesRef = useRef([]); // the node objects currently on screen (concepts or topics)
  const conceptNodesRef = useRef(null);
  const conceptLinksRef = useRef(null);
  const entranceRafRef = useRef(0);

  const showHistoryRef = useRef(true);
  const lastSnapRef = useRef(null);
  const prevLinkKeysRef = useRef(new Set()); // link set before the last ingest
  const recentKeysRef = useRef(new Set()); // facts added by the most recent ingest

  // focus mode — hover a node to spotlight it + neighbors, dim the rest
  const hoverNodeRef = useRef(null);
  const highlightNodesRef = useRef(new Set());
  const highlightLinksRef = useRef(new Set());
  const currentLinksRef = useRef([]);
  const selectedNodeRef = useRef(null); // sticky node selected by click
  const hoveredEdgeRef = useRef(null);

  // time slider — scrub to see the memory "as of" a date
  const asOfRef = useRef(0);
  const timeActiveRef = useRef(false);
  const [timeRange, setTimeRange] = useState({ min: 0, max: 0 });
  const [asOf, setAsOf] = useState(0);
  const [timeActive, setTimeActive] = useState(false);
  const DAY = 86400000;

  const linkKey = (l) => `${l.source}\t${l.target}\t${l.name}`;

  // ---- one-time 3D graph setup ----------------------------------------------
  useEffect(() => {
    const fg = new ForceGraph3D(containerRef.current)
      .backgroundColor("#000000")
      .linkOpacity(0.55)
      .linkCurvature(0.18) // gentle arcs, like the InfraNodus web
      .d3VelocityDecay(0.28) // less friction → nodes glide (smoother motion)
      .d3AlphaDecay(0.016) // cool the layout more gently so it eases into place
      .warmupTicks(0)
      .cooldownTime(16000)
      .nodeLabel(() => "") // node info goes to the left panel on hover, not a floating tooltip
      .nodeThreeObjectExtend(false)
      .nodeThreeObject((n) => {
        if (n.__isTopic) {
          // Topics view: a real 3D CUBE, rendered unlit → appears as a solid square but
          // occupies volume so edges are occluded (same idea as the concept spheres).
          const g = new THREE.Group();
          const c = 9 + Math.pow(n.val || 1, 0.65) * 4.6; // cube size by cluster size (bigger spread)
          const cube = new THREE.Mesh(
            new THREE.BoxGeometry(c, c, c),
            new THREE.MeshBasicMaterial({
              color: n.color || "#9fb0d0",
              transparent: true,
              depthWrite: true,
              fog: false,
            }),
          );
          cube.renderOrder = 3;
          g.add(cube);
          const labT = new SpriteText(n.name);
          labT.fontFace = "'Helvetica Neue', Helvetica, Arial, sans-serif";
          labT.fontWeight = "600";
          labT.color = n.color || "#eef2fb"; // topic label matches the cluster color
          labT.textHeight = 4 + Math.pow(n.val || 1, 0.6) * 1.1; // scales with cluster/cube size
          labT.center.set(0, 0.5); // to the right of the square
          n.__labelOff = c * 0.62 + 7; // clear the cube's corner + gap
          labT.position.set(n.__labelOff, 0, 0);
          labT.material.fog = false;
          labT.renderOrder = 6;
          g.add(labT);
          n.__disk = cube;
          n.__label = labT;
          n.__r = c;
          return g;
        }
        const group = new THREE.Group();
        const r = 3.5 + Math.pow(n.val || 1, 0.85) * 3.2; // size by connections
        n.__r = r;
        const entering = n.__enterT0 != null;
        // A real 3D SPHERE, rendered unlit → looks like a flat solid circle, but occupies
        // real volume: edges are occluded inside/behind it and only show once they exit the
        // sphere — correct from ANY camera angle (a flat billboard can't do this).
        const disk = new THREE.Mesh(
          new THREE.SphereGeometry(r / 2, 24, 18),
          new THREE.MeshBasicMaterial({
            color: n.color || "#9fb0d0",
            transparent: true,
            depthWrite: true, // occlude edges inside/behind the sphere
            fog: false,
          }),
        );
        disk.scale.setScalar(entering ? 0.01 : 1); // new nodes grow in from ~0
        if (entering) disk.material.opacity = 0;
        disk.renderOrder = 3;
        group.add(disk);
        const label = new SpriteText(n.name);
        label.fontFace = "'Helvetica Neue', Helvetica, Arial, sans-serif";
        label.fontWeight = "600";
        label.color = "#eef2fb"; // white names (InfraNodus-style)
        label.textHeight = 2.2 + Math.pow(n.val || 1, 0.75) * 0.9; // bigger for bigger nodes
        label.center.set(0, 0.5); // anchor at left-middle → the name sits to the RIGHT of the node
        n.__labelOff = r / 2 + 5.5; // gap from the node
        label.position.set(n.__labelOff, 0, 0);
        label.material.fog = false;
        label.renderOrder = 6;
        if (entering) {
          label.material.transparent = true;
          label.material.opacity = 0;
        }
        group.add(label);
        n.__disk = disk;
        n.__label = label;
        return group;
      })
      // Colorful web (InfraNodus-style): active edges take their source cluster's color;
      // just-added = white; no-longer-active = muted red. Focusing dims the rest to near-black.
      .linkColor((l) => {
        if (hoverNodeRef.current && !highlightLinksRef.current.has(l)) return "#20242e";
        if (l.recent) return "#ffffff";
        if (!l.is_current && !l.timeView) return "#000000"; // hide solid line — a dashed one is drawn instead
        if (l.__topic) return l.color || "#8aa0c8"; // topic edges: coloured by source cluster
        return l.__srcColor || "#6f86b3"; // active edges: coloured by source cluster
      })
      .linkWidth((l) => {
        const base = l.__topic
          ? 1.4 + Math.min(3, (l.weight || 1) * 0.5) // topic edges: thicker, by cross-cluster weight
          : l.recent
            ? 1.4
            : l.is_current || l.timeView
              ? 0.6
              : 0.4;
        return hoverNodeRef.current && highlightLinksRef.current.has(l) ? base + 1.1 : base;
      })
      .linkLabel(() => "") // edge info goes to the left panel on hover
      // Flowing particle animation along the active edges.
      .linkDirectionalParticles((l) => {
        if (hoverNodeRef.current && !highlightLinksRef.current.has(l)) return 0;
        return l.is_current || l.recent || l.timeView ? 2 : 0;
      })
      .linkDirectionalParticleWidth(1.8)
      .linkDirectionalParticleSpeed(0.006)
      // Only no-longer-active facts get a custom object: a thick dashed red line (Line2).
      // Relationship NAMES are never drawn on the graph — they show in the left panel on hover.
      .linkThreeObjectExtend(true)
      .linkThreeObject((l) => {
        if (l.is_current || l.timeView) {
          l.__dash = null;
          return null;
        }
        const geom = new LineGeometry();
        geom.setPositions([0, 0, 0, 0.01, 0, 0]);
        const srcColor = l.__srcColor || "#ff6b8a";
        const line = new Line2(
          geom,
          new LineMaterial({
            color: new THREE.Color(srcColor), // dashed edge takes its source node's colour
            linewidth: 0.8, // match the normal (active) edge thickness, just dashed
            worldUnits: true,
            dashed: true,
            dashSize: 1.4,
            gapSize: 1.1,
            transparent: true,
            opacity: 1,
          }),
        );
        line.computeLineDistances();
        l.__dash = line;
        return line;
      })
      .linkPositionUpdate((obj, { start, end }, link) => {
        if (link.__dash) {
          link.__dash.geometry.setPositions([start.x, start.y, start.z, end.x, end.y, end.z]);
          link.__dash.computeLineDistances(); // required for the dashes to render
        }
      })
      // Hover a node → show its info in the left panel (no floating tooltip).
      .onNodeHover((node) => {
        setHoveredNode(node ? { name: node.name, summary: node.summary || "", color: node.color || "#9fb0d0" } : null);
      })
      // Click a node to focus it. Once something is focused, clicking ANYWHERE (any node
      // or empty space) clears the focus.
      .onNodeClick((node) => {
        if (selectedNodeRef.current) {
          selectedNodeRef.current = null;
          focusNode(null);
        } else {
          selectedNodeRef.current = node;
          focusNode(node);
        }
      })
      .onBackgroundClick(() => {
        selectedNodeRef.current = null;
        focusNode(null);
      })
      // Hover an edge → its fact appears in the left panel (no on-graph label).
      .onLinkHover((link) => {
        setHoveredFact(
          link
            ? {
                source: typeof link.source === "object" ? link.source.name : link.source,
                target: typeof link.target === "object" ? link.target.name : link.target,
                name: link.name,
                fact: link.fact,
                is_current: link.is_current,
                invalid_at: link.invalid_at,
              }
            : null,
        );
      });
    fgRef.current = fg;

    // Per-frame loop: (1) smooth entrance grow/fade for new nodes; (2) keep every label to
    // the camera's RIGHT so it stays on the right of the node from any angle (screen-space).
    const camRight = new THREE.Vector3();
    const entranceStep = () => {
      const cam = fgRef.current && fgRef.current.camera();
      if (cam) camRight.setFromMatrixColumn(cam.matrixWorld, 0).normalize();
      const now = performance.now();
      for (const n of renderedNodesRef.current) {
        if (n.__enterT0 != null) {
          const p = Math.min(1, (now - n.__enterT0) / 650);
          const e = 1 - Math.pow(1 - p, 3);
          const r = n.__r || 8;
          if (n.__disk) {
            n.__disk.scale.setScalar(e);
            n.__disk.material.opacity = e;
          }
          if (n.__label) {
            n.__label.material.transparent = true;
            n.__label.material.opacity = e;
          }
          if (p >= 1) n.__enterT0 = null;
        }
        if (n.__label && cam) {
          const off = n.__labelOff || (n.__r || 8) / 2 + 5.5;
          n.__label.position.set(camRight.x * off, camRight.y * off, camRight.z * off);
        }
      }
      entranceRafRef.current = requestAnimationFrame(entranceStep);
    };
    entranceRafRef.current = requestAnimationFrame(entranceStep);

    // Lighter, snappier camera — the default rotation felt heavy.
    const controls = fg.controls();
    if (controls) {
      controls.rotateSpeed = 2.4;
      controls.zoomSpeed = 3.4; // faster zoom in/out
      controls.panSpeed = 1.2;
      controls.dynamicDampingFactor = 0.35;
    }

    // Depth cue — geometry further from the camera fades toward black, so whatever
    // faces the screen stands out and the rest goes shady (like the video).
    fg.scene().fog = new THREE.FogExp2(0x000000, 0.0011);
    // Bright ambient so the LIT edge cylinders show their full colour (nodes are unlit).
    fg.scene().add(new THREE.AmbientLight(0xffffff, 2.2));

    const resize = () => {
      const el = containerRef.current;
      if (el) fg.width(el.clientWidth).height(el.clientHeight);
    };
    resize();
    window.addEventListener("resize", resize);

    if (new URLSearchParams(window.location.search).get("mode") === "topics") {
      viewModeRef.current = "topics";
      setViewMode("topics");
    }
    loadInitial();
    fetchModels().then(({ models: list }) => setModels(list)).catch(() => {});

    return () => {
      window.removeEventListener("resize", resize);
      cancelAnimationFrame(entranceRafRef.current);
      fg._destructor?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadInitial() {
    try {
      const snap = await getGraph();
      prevLinkKeysRef.current = new Set(snap.links.map(linkKey)); // seed: nothing is "recent" on load
      applySnapshot(snap);
      setStatus(snap.stats.node_count ? "" : "Empty — drop a PDF or paste text to build the memory.");
      // Deep-link / demo: ?demoSelect=1 auto-focuses the most-connected entity on load.
      if (new URLSearchParams(window.location.search).get("demoSelect") && nodesRef.current.size) {
        const top = [...nodesRef.current.values()].sort((a, b) => (b.val || 0) - (a.val || 0))[0];
        if (top)
          setTimeout(() => {
            selectedNodeRef.current = top;
            focusNode(top);
          }, 1500);
      }
    } catch (e) {
      setError(`Couldn't load the graph: ${e.message}`);
      setStatus("");
    }
  }

  // Sync the 3D data to a snapshot, reusing node objects so existing entities keep
  // their 3D positions while new ones fly in.
  function applySnapshot(snap) {
    lastSnapRef.current = snap;
    const byId = nodesRef.current;
    const incoming = new Set(snap.nodes.map((n) => n.id));
    for (const id of [...byId.keys()]) if (!incoming.has(id)) byId.delete(id);

    // For a smooth entrance, spawn each new node at the position of a node it connects
    // to, so it grows outward from its "parent" rather than popping in at the center.
    const existingIds = new Set(byId.keys());
    const parentOf = {};
    for (const l of snap.links) {
      if (!existingIds.has(l.source) && existingIds.has(l.target)) parentOf[l.source] = l.target;
      else if (!existingIds.has(l.target) && existingIds.has(l.source)) parentOf[l.target] = l.source;
    }
    const jitter = () => (Math.random() - 0.5) * 4;
    for (const n of snap.nodes) {
      const ex = byId.get(n.id);
      if (ex) {
        ex.name = n.name;
        ex.summary = n.summary;
      } else {
        const parent = parentOf[n.id] ? byId.get(parentOf[n.id]) : null;
        const px = parent && parent.x != null ? parent.x : jitter();
        const py = parent && parent.y != null ? parent.y : jitter();
        const pz = parent && parent.z != null ? parent.z : jitter();
        byId.set(n.id, {
          id: n.id,
          name: n.name,
          summary: n.summary,
          labels: n.labels,
          x: px + jitter(),
          y: py + jitter(),
          z: pz + jitter(),
          __enterT0: performance.now(), // drives the grow/fade-in animation
        });
      }
    }

    // Recency: facts present now but not before the last ingest are "recent".
    const allKeys = new Set(snap.links.map(linkKey));
    const newKeys = [...allKeys].filter((k) => !prevLinkKeysRef.current.has(k));
    if (newKeys.length) {
      recentKeysRef.current = new Set(newKeys);
      timeActiveRef.current = false; // new knowledge → jump back to live
      setTimeActive(false);
    }
    prevLinkKeysRef.current = allKeys;

    // Timeline = INGESTION history (created_at), so scrubbing shows the graph as it grew
    // with each upload — to the minute, not just the day.
    let tmin = Infinity;
    let tmax = Date.now();
    for (const l of snap.links) {
      if (l.created_at) tmin = Math.min(tmin, Date.parse(l.created_at));
      if (l.invalid_at) tmax = Math.max(tmax, Date.parse(l.invalid_at));
    }
    if (!isFinite(tmin)) tmin = tmax - DAY;
    setTimeRange((r) => (r.min === tmin && r.max === tmax ? r : { min: tmin, max: tmax }));

    let links = snap.links.map((l) => ({
      source: l.source,
      target: l.target,
      name: l.name,
      fact: l.fact,
      is_current: l.is_current,
      valid_at: l.valid_at,
      invalid_at: l.invalid_at,
      created_at: l.created_at,
      recent: recentKeysRef.current.has(linkKey(l)),
    }));

    if (timeActiveRef.current) {
      // Evolution view: the graph as it was known at the scrubbed instant — facts created
      // by then and not yet invalidated.
      const t = asOfRef.current;
      links = links.filter((l) => {
        const c = l.created_at ? Date.parse(l.created_at) : -Infinity;
        const iv = l.invalid_at ? Date.parse(l.invalid_at) : Infinity;
        return c <= t && t < iv;
      });
      links.forEach((l) => (l.timeView = true));
    } else if (!showHistoryRef.current) {
      links = links.filter((l) => l.is_current);
    }

    const nodes = [...byId.values()];

    // Cross-references for focus mode: each node's neighbors + incident links.
    nodes.forEach((n) => {
      n.__neighbors = [];
      n.__adjLinks = [];
    });
    for (const l of links) {
      const a = byId.get(l.source);
      const b = byId.get(l.target);
      if (a && b) {
        a.__neighbors.push(b);
        b.__neighbors.push(a);
        a.__adjLinks.push(l);
        b.__adjLinks.push(l);
      }
    }
    currentLinksRef.current = links;

    enrich(nodes, links);
    // Store each edge's source-cluster colour as a plain string NOW (reliable), before
    // the graph binds l.source to the node object (accessors were reading it too early).
    for (const l of links) l.__srcColor = byId.get(l.source)?.color || "#6f86b3";
    conceptNodesRef.current = nodes;
    conceptLinksRef.current = links;
    renderView(); // draw as concepts or topics, per the current view mode
    setStats(snap.stats);
  }

  // Draw the current view: individual entities (concepts) or one cube per Louvain
  // cluster (topics). Both reuse the same focus/hover machinery via renderedNodesRef.
  function renderView() {
    const nodes = conceptNodesRef.current;
    const links = conceptLinksRef.current;
    if (!nodes) return;
    if (viewModeRef.current === "topics") {
      const t = topicsFrom(nodes, links);
      const byId = {};
      t.nodes.forEach((n) => {
        n.__neighbors = [];
        n.__adjLinks = [];
        byId[n.id] = n;
      });
      t.links.forEach((l) => {
        const a = byId[l.source];
        const b = byId[l.target];
        if (a && b) {
          a.__neighbors.push(b);
          b.__neighbors.push(a);
          a.__adjLinks.push(l);
          b.__adjLinks.push(l);
        }
      });
      renderedNodesRef.current = t.nodes;
      currentLinksRef.current = t.links;
      fgRef.current.graphData({ nodes: t.nodes, links: t.links });
    } else {
      renderedNodesRef.current = nodes;
      currentLinksRef.current = links;
      fgRef.current.graphData({ nodes, links });
    }

    // Spread the topic squares far apart; normal spacing for concepts.
    const fg = fgRef.current;
    const charge = fg.d3Force("charge");
    const linkF = fg.d3Force("link");
    if (viewModeRef.current === "topics") {
      if (charge) charge.strength(-750); // spread the few topic squares apart, but on-screen
      if (linkF) linkF.distance(95);
    } else {
      if (charge) charge.strength(-130);
      if (linkF) linkF.distance(32);
    }
    fg.d3ReheatSimulation();
  }

  function setView(mode) {
    if (mode === viewModeRef.current) return;
    viewModeRef.current = mode;
    setViewMode(mode);
    selectedNodeRef.current = null;
    focusNode(null); // clear any focus when switching views
    renderView();
  }

  // Spotlight the hovered node + neighbors; dim the rest. Node disks/labels are custom
  // objects, so we fade their materials directly; link lines go through the accessors.
  // A node's "group" = its Louvain community, named by the community's most important
  // member. Shown in the left inspector panel on click.
  function buildSelection(node) {
    if (!node) return null;
    if (node.__isTopic) {
      return {
        nodeName: node.name,
        color: node.color || "#9fb0d0",
        groupName: node.name,
        members: node.members || [],
        factCount: (node.__adjLinks || []).length,
      };
    }
    const all = [...nodesRef.current.values()];
    const comm = node.community ?? 0;
    const members = all.filter((n) => (n.community ?? 0) === comm);
    const top = members.reduce((a, b) => ((b.val || 0) > (a.val || 0) ? b : a), members[0] || node);
    return {
      nodeName: node.name,
      color: node.color || "#9fb0d0",
      groupName: (top && top.name) || node.name,
      members: members.map((m) => m.name).sort((a, b) => a.localeCompare(b)),
      factCount: (node.__adjLinks || []).length,
    };
  }

  // Compute the focus set (node + neighbors + incident edges) and apply it.
  function focusNode(node) {
    const hn = highlightNodesRef.current;
    const hl = highlightLinksRef.current;
    hn.clear();
    hl.clear();
    if (node) {
      hn.add(node);
      (node.__neighbors || []).forEach((n) => hn.add(n));
      (node.__adjLinks || []).forEach((l) => hl.add(l));
    }
    hoverNodeRef.current = node || null;
    applyFocus();
    setSelection(node ? buildSelection(node) : null);
    setHoveredFact(null);
  }

  function applyFocus() {
    const focusing = !!hoverNodeRef.current;
    const hn = highlightNodesRef.current;
    const hl = highlightLinksRef.current;
    for (const n of renderedNodesRef.current) {
      const on = !focusing || hn.has(n);
      if (n.__disk) n.__disk.material.opacity = on ? 1 : 0.2; // dim, but still see behind
      if (n.__label) {
        n.__label.material.transparent = true;
        n.__label.material.opacity = on ? 1 : 0.12;
      }
    }
    for (const l of currentLinksRef.current) {
      // Dashed "no-longer-active" lines fade when out of focus.
      if (l.__dash) l.__dash.material.opacity = !focusing || hl.has(l) ? 1 : 0.08;
    }
    const fg = fgRef.current;
    fg.linkColor(fg.linkColor()).linkWidth(fg.linkWidth()).linkDirectionalParticles(fg.linkDirectionalParticles());
  }

  function toggleHistory() {
    showHistoryRef.current = !showHistoryRef.current;
    setShowHistory(showHistoryRef.current);
    if (lastSnapRef.current) applySnapshot(lastSnapRef.current);
  }

  function scrubTo(v) {
    const atMax = v >= timeRange.max;
    asOfRef.current = v;
    timeActiveRef.current = !atMax;
    setAsOf(v);
    setTimeActive(!atMax);
    if (lastSnapRef.current) applySnapshot(lastSnapRef.current);
  }

  function goLive() {
    timeActiveRef.current = false;
    setTimeActive(false);
    if (lastSnapRef.current) applySnapshot(lastSnapRef.current);
  }

  async function handleFiles(files) {
    const pdfs = [...files].filter((f) => f.name.toLowerCase().endsWith(".pdf"));
    if (!pdfs.length) {
      setError("Only PDF files are supported here.");
      return;
    }
    setError("");
    setBusy(true);
    try {
      for (const file of pdfs) {
        await uploadPdfStream(file, model, (ev) => {
          if (ev.phase === "parsing") setStatus(`Reading “${file.name}”…`);
          else if (ev.phase === "parsed") setStatus(`Extracting ${ev.pages} page${ev.pages === 1 ? "" : "s"}…`);
          else if (ev.phase === "page") {
            applySnapshot(ev);
            setStatus(`Page ${ev.page}/${ev.total} — ${ev.stats.node_count} entities, ${ev.stats.edge_count} facts`);
          } else if (ev.phase === "error") setError(ev.detail);
          else if (ev.phase === "done") setStatus(`Done — “${file.name}” folded in.`);
        });
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleAddText() {
    if (!text.trim()) return;
    setError("");
    setBusy(true);
    setStatus("Extracting entities & relationships… (the strong model takes ~20–40s)");
    try {
      const snap = await ingestText(text.trim(), model, "pasted text");
      applySnapshot(snap);
      setText("");
      setStatus(`Added — ${snap.stats.node_count} entities, ${snap.stats.edge_count} facts.`);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleReset() {
    setBusy(true);
    setStatus("Clearing memory…");
    try {
      prevLinkKeysRef.current = new Set();
      recentKeysRef.current = new Set();
      const snap = await resetGraph();
      applySnapshot(snap);
      setStatus("Empty — drop a PDF or paste text to build the memory.");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function onDrop(e) {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files?.length) handleFiles(e.dataTransfer.files);
  }

  // ---- save / restore checkpoints -------------------------------------------
  async function refreshSaves() {
    try {
      setSaves((await listSaves()).saves || []);
    } catch {
      /* ignore */
    }
  }

  function toggleSaves() {
    setSavesOpen((o) => {
      if (!o) refreshSaves();
      return !o;
    });
  }

  async function handleSave() {
    const name = saveName.trim();
    if (!name) return;
    setError("");
    setBusy(true);
    setStatus(`Saving “${name}”…`);
    try {
      await saveGraph(name);
      setSaveName("");
      await refreshSaves();
      setStatus(`Saved “${name}”.`);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleRestore(name) {
    setError("");
    setBusy(true);
    setStatus(`Restoring “${name}”…`);
    try {
      const snap = await restoreGraph(name);
      recentKeysRef.current = new Set();
      prevLinkKeysRef.current = new Set(snap.links.map(linkKey)); // restored facts aren't "new"
      applySnapshot(snap);
      setSavesOpen(false);
      setStatus(`Restored “${name}”.`);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteSave(name) {
    try {
      await deleteSave(name);
      await refreshSaves();
    } catch (e) {
      setError(e.message);
    }
  }

  // Timeline granularity: fine steps + a time-of-day label when the whole history spans
  // less than ~2 days (e.g. several uploads in one day), coarser when it spans longer.
  const timeSpan = timeRange.max - timeRange.min;
  const sliderStep = timeSpan < 2 * DAY ? 60000 : timeSpan < 90 * DAY ? 3600000 : DAY;
  const fmtStamp = (ms) => {
    const d = new Date(ms);
    const date = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    if (timeSpan >= 2 * DAY) return date;
    return `${date} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  };

  // Left-panel detail: a hovered edge's fact, else a hovered node's info, else a hint.
  const factCard = hoveredFact && (
    <div>
      <div style={{ fontFamily: "ui-monospace, monospace", fontSize: 11, color: "#9b8cff", marginBottom: 4 }}>
        {hoveredFact.source} —{hoveredFact.name}→ {hoveredFact.target}
      </div>
      <div style={{ fontSize: 12.5, color: "#dfe7f5", lineHeight: 1.5 }}>{hoveredFact.fact}</div>
      {hoveredFact.invalid_at && (
        <div style={{ fontSize: 11, color: "#ff8da3", marginTop: 4 }}>
          no longer active · {hoveredFact.invalid_at.slice(0, 10)}
        </div>
      )}
    </div>
  );
  const nodeCard = hoveredNode && (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 5 }}>
        <span style={{ width: 10, height: 10, borderRadius: "50%", background: hoveredNode.color, flexShrink: 0 }} />
        <span style={{ fontSize: 13, fontWeight: 700, color: "#eef2fb" }}>{hoveredNode.name}</span>
      </div>
      {hoveredNode.summary ? (
        <div style={{ fontSize: 12, color: "#c2cbe2", lineHeight: 1.5, whiteSpace: "pre-line" }}>{hoveredNode.summary}</div>
      ) : (
        <div style={{ fontSize: 11.5, color: "#6b7693" }}>No summary yet.</div>
      )}
    </div>
  );
  const detail = hoveredFact
    ? factCard
    : hoveredNode
      ? nodeCard
      : selection
        ? <div style={{ fontSize: 11.5, color: "#6b7693" }}>Hover a node or edge to read it.</div>
        : null;

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={onDrop}
      style={{
        position: "fixed",
        inset: 0,
        background: "#070912",
        color: "#e7ecf7",
        fontFamily: "Inter, system-ui, sans-serif",
        overflow: "hidden",
      }}
    >
      <div ref={containerRef} style={{ position: "absolute", inset: 0 }} />

      {/* top bar */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "12px 18px",
          background: "linear-gradient(180deg, rgba(7,9,18,0.85), rgba(7,9,18,0))",
          pointerEvents: "none",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 9, pointerEvents: "auto" }}>
          <span style={{ color: "#5cc8ff", fontSize: 18 }}>◆</span>
          <span style={{ fontWeight: 600, fontSize: 15 }}>Noema · Graph Memory</span>
          <span style={{ fontSize: 11, color: "#6b7693", marginLeft: 4 }}>Graphiti · 3D</span>
        </div>

        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 14, pointerEvents: "auto" }}>
          {stats && (
            <span style={{ fontSize: 12.5, color: "#9aa6c2" }}>
              <b style={{ color: "#e7ecf7" }}>{stats.node_count}</b> entities ·{" "}
              <b style={{ color: "#e7ecf7" }}>{stats.current_edges}</b> facts
              {stats.invalidated_edges > 0 && (
                <span style={{ color: "#ff6b8a" }}> · {stats.invalidated_edges} invalidated</span>
              )}
            </span>
          )}
          <div style={{ position: "relative" }}>
            <button onClick={toggleSaves} disabled={busy} style={ghostBtn}>
              ⧉ Saves{saves.length ? ` (${saves.length})` : ""}
            </button>
            {savesOpen && (
              <div style={savesPanel}>
                <div style={{ fontSize: 11, color: "#7a87a6", marginBottom: 6 }}>Save current graph</div>
                <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
                  <input
                    value={saveName}
                    onChange={(e) => setSaveName(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleSave()}
                    placeholder="name this checkpoint…"
                    disabled={busy}
                    style={{
                      flex: 1,
                      minWidth: 0,
                      background: "rgba(7,10,20,0.7)",
                      border: "1px solid rgba(120,135,175,0.2)",
                      borderRadius: 8,
                      padding: "5px 8px",
                      color: "#e7ecf7",
                      fontSize: 12,
                      outline: "none",
                    }}
                  />
                  <button
                    onClick={handleSave}
                    disabled={busy || !saveName.trim()}
                    style={{ ...primaryBtn, width: "auto", padding: "5px 12px", opacity: busy || !saveName.trim() ? 0.5 : 1 }}
                  >
                    Save
                  </button>
                </div>
                <div style={{ fontSize: 11, color: "#7a87a6", marginBottom: 4, borderTop: "1px solid rgba(120,135,175,0.15)", paddingTop: 8 }}>
                  Saved checkpoints
                </div>
                {saves.length === 0 ? (
                  <div style={{ fontSize: 11.5, color: "#6b7693", padding: "4px 0" }}>None yet.</div>
                ) : (
                  saves.map((s) => (
                    <div key={s} style={{ display: "flex", alignItems: "center", gap: 6, padding: "3px 0" }}>
                      <span style={{ flex: 1, minWidth: 0, fontSize: 12.5, color: "#e7ecf7", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {s}
                      </span>
                      <button onClick={() => handleRestore(s)} disabled={busy} style={{ ...ghostBtn, padding: "3px 9px", fontSize: 11.5 }}>
                        Restore
                      </button>
                      <button
                        onClick={() => handleDeleteSave(s)}
                        title="Delete this save"
                        style={{ ...ghostBtn, padding: "3px 7px", color: "#ff9db0" }}
                      >
                        ✕
                      </button>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
          {confirmReset ? (
            <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 12, color: "#ff8da3" }}>Clear the whole memory?</span>
              <button
                onClick={() => {
                  setConfirmReset(false);
                  handleReset();
                }}
                disabled={busy}
                style={{
                  ...ghostBtn,
                  background: "rgba(255,90,110,0.18)",
                  border: "1px solid rgba(255,90,110,0.4)",
                  color: "#ff9db0",
                }}
              >
                Yes, reset
              </button>
              <button onClick={() => setConfirmReset(false)} style={ghostBtn}>
                Cancel
              </button>
            </span>
          ) : (
            <button onClick={() => setConfirmReset(true)} disabled={busy} style={ghostBtn}>
              Reset
            </button>
          )}
          <a href={`${window.location.origin}/`} style={{ ...ghostBtn, textDecoration: "none" }}>
            Open chat ↗
          </a>
        </div>
      </div>

      {/* view toolbar — whole graph (concepts) vs. clusters (topics) */}
      <div style={viewToolbar}>
        {[
          ["◦ Concepts", "concepts"],
          ["▦ Topics", "topics"],
        ].map(([label, mode]) => (
          <button
            key={mode}
            onClick={() => setView(mode)}
            style={{
              padding: "6px 15px",
              fontSize: 12.5,
              fontWeight: 600,
              border: "none",
              cursor: "pointer",
              background: viewMode === mode ? "rgba(92,200,255,0.18)" : "transparent",
              color: viewMode === mode ? "#bfe4ff" : "#9aa6c2",
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {/* left panel — group inspector on click, node/edge info on hover */}
      {(selection || hoveredNode || hoveredFact) && (
        <div style={leftPanel}>
          {selection ? (
            <>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                <span style={{ width: 11, height: 11, borderRadius: "50%", background: selection.color, flexShrink: 0 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 10, color: "#7a87a6", textTransform: "uppercase", letterSpacing: 0.4 }}>Group</div>
                  <div
                    style={{
                      fontSize: 14,
                      fontWeight: 700,
                      color: "#eef2fb",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {selection.groupName}
                  </div>
                </div>
                <button
                  onClick={() => {
                    selectedNodeRef.current = null;
                    focusNode(null);
                  }}
                  style={{ ...ghostBtn, padding: "2px 8px" }}
                >
                  ✕
                </button>
              </div>

              <div style={{ fontSize: 12, color: "#9aa6c2", marginBottom: 10 }}>
                Selected: <b style={{ color: "#cfe0ff" }}>{selection.nodeName}</b> · {selection.factCount} fact
                {selection.factCount === 1 ? "" : "s"}
              </div>

              <div style={{ fontSize: 10, color: "#7a87a6", marginBottom: 4 }}>Entities in this group</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginBottom: 12 }}>
                {selection.members.map((m) => (
                  <span
                    key={m}
                    style={{
                      fontSize: 11,
                      padding: "2px 8px",
                      borderRadius: 999,
                      background: m === selection.nodeName ? "rgba(92,200,255,0.18)" : "rgba(120,135,175,0.12)",
                      color: m === selection.nodeName ? "#bfe4ff" : "#c2cbe2",
                    }}
                  >
                    {m}
                  </span>
                ))}
              </div>

              <div style={{ borderTop: "1px solid rgba(120,135,175,0.15)", paddingTop: 10 }}>{detail}</div>
            </>
          ) : (
            detail
          )}
        </div>
      )}

      {/* inject panel */}
      <div
        style={{
          position: "absolute",
          left: 18,
          bottom: 18,
          width: 320,
          background: "rgba(13,18,32,0.85)",
          border: "1px solid rgba(120,135,175,0.18)",
          borderRadius: 14,
          padding: 14,
          backdropFilter: "blur(10px)",
          boxShadow: "0 12px 40px rgba(0,0,0,0.5)",
        }}
      >
        <div style={{ fontSize: 12.5, fontWeight: 600, color: "#c2cbe2", marginBottom: 8 }}>
          Build the memory
        </div>

        <div style={{ marginBottom: 9 }}>
          <div style={{ fontSize: 10.5, color: "#7a87a6", marginBottom: 4 }}>
            Extraction model · builds the graph
          </div>
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            disabled={busy}
            title="The model that extracts entities + relationships from text. Use a strong model (e.g. gpt-4.1); PDFs are read by the default vision model."
            style={selectStyle}
          >
            <option value="" style={{ color: "#0a0e1a" }}>
              Default (strong · gpt-4o)
            </option>
            {models.map((m) => (
              <option key={m} value={m} style={{ color: "#0a0e1a" }}>
                {m}
              </option>
            ))}
          </select>
        </div>

        <button
          onClick={toggleHistory}
          style={{
            ...ghostBtn,
            width: "100%",
            marginBottom: 9,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 7,
            color: showHistory ? "#cdd5ea" : "#7a87a6",
          }}
          title="Show or hide facts that are no longer active (Graphiti keeps them — they're never deleted)"
        >
          <span
            style={{
              width: 9,
              height: 9,
              borderRadius: 3,
              background: showHistory ? "#ff6b8a" : "transparent",
              border: "1.5px solid #ff6b8a",
            }}
          />
          {showHistory ? "Showing no-longer-active facts" : "Hiding no-longer-active facts"}
        </button>

        <label style={uploadBtn}>
          <input
            type="file"
            accept="application/pdf,.pdf"
            multiple
            disabled={busy}
            style={{ display: "none" }}
            onChange={(e) => {
              if (e.target.files?.length) handleFiles(e.target.files);
              e.target.value = "";
            }}
          />
          ⬆ Upload PDF(s)
        </label>

        <div style={{ fontSize: 11, color: "#6b7693", textAlign: "center", margin: "8px 0" }}>
          or drop a PDF anywhere · or paste text
        </div>

        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Paste a paragraph to extract into the graph…"
          rows={3}
          disabled={busy}
          style={textareaStyle}
        />
        <button
          onClick={handleAddText}
          disabled={busy || !text.trim()}
          style={{ ...primaryBtn, opacity: busy || !text.trim() ? 0.5 : 1, marginTop: 8 }}
        >
          Extract into graph
        </button>

        {(status || error) && (
          <div
            style={{
              marginTop: 10,
              fontSize: 11.5,
              color: error ? "#ff8da3" : "#8fd6c2",
              display: "flex",
              alignItems: "center",
              gap: 7,
            }}
          >
            {busy && <span style={spinner} />}
            {error || status}
          </div>
        )}
      </div>

      {/* legend */}
      <div
        style={{
          position: "absolute",
          right: 18,
          bottom: 18,
          fontSize: 11,
          color: "#8a93ad",
          background: "rgba(13,18,32,0.7)",
          border: "1px solid rgba(120,135,175,0.15)",
          borderRadius: 10,
          padding: "8px 11px",
          lineHeight: 1.7,
        }}
      >
        <div>
          <span style={{ color: "#ffffff" }}>──▶</span> just added
        </div>
        <div>
          <span style={{ color: "#96c8ff" }}>──▶</span> active fact
        </div>
        <div>
          <span style={{ color: "#ff6b8a" }}>╌╌▶</span> no longer active
        </div>
        <div style={{ color: "#6b7693", marginTop: 3 }}>color = cluster · size = connections · hover to focus</div>
      </div>

      {/* time slider — scrub the memory's history */}
      {timeRange.max > timeRange.min && stats?.edge_count > 0 && (
        <div style={timeBar}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 5 }}>
            <span style={{ fontSize: 11, color: "#8a93ad" }}>
              {timeActive ? "memory as of " : "now · "}
              <b style={{ color: timeActive ? "#ffd166" : "#8fd6c2" }}>
                {fmtStamp(timeActive ? asOf : timeRange.max)}
              </b>
            </span>
            <button onClick={goLive} style={{ ...ghostBtn, padding: "3px 9px", opacity: timeActive ? 1 : 0.45 }}>
              ● Live
            </button>
          </div>
          <input
            type="range"
            min={timeRange.min}
            max={timeRange.max}
            step={sliderStep}
            value={timeActive ? asOf : timeRange.max}
            onChange={(e) => scrubTo(Number(e.target.value))}
            style={{ width: "100%", accentColor: "#5cc8ff", cursor: "pointer" }}
          />
          <div style={{ fontSize: 10, color: "#6b7693", textAlign: "center", marginTop: 2 }}>
            scrub to see the memory as it was on a date
          </div>
        </div>
      )}

      {dragOver && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "grid",
            placeItems: "center",
            background: "rgba(8,12,24,0.74)",
            border: "2px dashed rgba(92,200,255,0.6)",
            fontSize: 18,
            color: "#bfe4ff",
            pointerEvents: "none",
          }}
        >
          Drop PDF to extract into the memory
        </div>
      )}

      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}

const ghostBtn = {
  background: "rgba(120,135,175,0.12)",
  border: "1px solid rgba(120,135,175,0.22)",
  color: "#cdd5ea",
  fontSize: 12.5,
  fontWeight: 500,
  padding: "5px 11px",
  borderRadius: 8,
  cursor: "pointer",
};

const selectStyle = {
  width: "100%",
  background: "rgba(7,10,20,0.7)",
  border: "1px solid rgba(120,135,175,0.2)",
  borderRadius: 8,
  padding: "6px 8px",
  color: "#e7ecf7",
  fontSize: 12,
  outline: "none",
  cursor: "pointer",
};

const textareaStyle = {
  width: "100%",
  resize: "none",
  background: "rgba(7,10,20,0.7)",
  border: "1px solid rgba(120,135,175,0.2)",
  borderRadius: 9,
  padding: "8px 10px",
  color: "#e7ecf7",
  fontSize: 12.5,
  outline: "none",
};

const uploadBtn = {
  display: "block",
  textAlign: "center",
  background: "rgba(92,200,255,0.14)",
  border: "1px solid rgba(92,200,255,0.35)",
  color: "#bfe4ff",
  fontSize: 13,
  fontWeight: 600,
  padding: "9px 0",
  borderRadius: 9,
  cursor: "pointer",
};

const primaryBtn = {
  width: "100%",
  background: "linear-gradient(95deg,#5cc8ff,#9b8cff)",
  border: "none",
  color: "#0a0e1a",
  fontSize: 13,
  fontWeight: 700,
  padding: "9px 0",
  borderRadius: 9,
  cursor: "pointer",
};

const savesPanel = {
  position: "absolute",
  top: 34,
  right: 0,
  width: 280,
  background: "rgba(13,18,32,0.96)",
  border: "1px solid rgba(120,135,175,0.22)",
  borderRadius: 12,
  padding: 12,
  backdropFilter: "blur(10px)",
  boxShadow: "0 12px 40px rgba(0,0,0,0.5)",
  zIndex: 20,
};

const viewToolbar = {
  position: "absolute",
  top: 58,
  left: "50%",
  transform: "translateX(-50%)",
  display: "flex",
  background: "rgba(13,18,32,0.85)",
  border: "1px solid rgba(120,135,175,0.2)",
  borderRadius: 10,
  overflow: "hidden",
  backdropFilter: "blur(10px)",
};

const leftPanel = {
  position: "absolute",
  left: 18,
  top: 64,
  width: 320,
  maxHeight: "46vh",
  overflowY: "auto",
  background: "rgba(13,18,32,0.92)",
  border: "1px solid rgba(120,135,175,0.2)",
  borderRadius: 14,
  padding: 14,
  backdropFilter: "blur(10px)",
  boxShadow: "0 12px 40px rgba(0,0,0,0.5)",
};

const timeBar = {
  position: "absolute",
  left: "50%",
  transform: "translateX(-50%)",
  bottom: 18,
  width: "min(520px, 42vw)",
  background: "rgba(13,18,32,0.85)",
  border: "1px solid rgba(120,135,175,0.18)",
  borderRadius: 12,
  padding: "10px 14px",
  backdropFilter: "blur(10px)",
  boxShadow: "0 12px 40px rgba(0,0,0,0.5)",
};

const spinner = {
  width: 11,
  height: 11,
  border: "2px solid rgba(143,214,194,0.35)",
  borderTopColor: "#8fd6c2",
  borderRadius: "50%",
  display: "inline-block",
  animation: "spin 0.7s linear infinite",
};

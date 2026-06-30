import { useEffect, useRef, useState } from "react";
import ForceGraph3D from "3d-force-graph";
import SpriteText from "three-spritetext";
import * as THREE from "three";

import { getGraph, ingestText, uploadPdfStream, resetGraph } from "../api/graphmem.js";
import { fetchModels } from "../api/models.js";
import { enrich } from "./graph3d.js";

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
  g.addColorStop(0.9, "rgba(255,255,255,1)");
  g.addColorStop(0.97, "rgba(255,255,255,0.95)");
  g.addColorStop(1, "rgba(255,255,255,0)");
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

  const showHistoryRef = useRef(true);
  const lastSnapRef = useRef(null);
  const prevLinkKeysRef = useRef(new Set()); // link set before the last ingest
  const recentKeysRef = useRef(new Set()); // facts added by the most recent ingest

  // focus mode — hover a node to spotlight it + neighbors, dim the rest
  const hoverNodeRef = useRef(null);
  const highlightNodesRef = useRef(new Set());
  const highlightLinksRef = useRef(new Set());
  const currentLinksRef = useRef([]);

  // time slider — scrub to see the memory "as of" a date
  const asOfRef = useRef(0);
  const timeActiveRef = useRef(false);
  const [timeRange, setTimeRange] = useState({ min: 0, max: 0 });
  const [asOf, setAsOf] = useState(0);
  const [timeActive, setTimeActive] = useState(false);
  const DAY = 86400000;
  const fmtDate = (ms) => new Date(ms).toISOString().slice(0, 10);

  const linkKey = (l) => `${l.source}\t${l.target}\t${l.name}`;

  // ---- one-time 3D graph setup ----------------------------------------------
  useEffect(() => {
    const fg = new ForceGraph3D(containerRef.current)
      .backgroundColor("#070912")
      .nodeLabel((n) => `<b>${n.name}</b>${n.summary ? `<br/><span style="opacity:.7">${n.summary}</span>` : ""}`)
      .nodeThreeObjectExtend(false)
      .nodeThreeObject((n) => {
        const group = new THREE.Group();
        const r = 5 + Math.sqrt(n.val || 1) * 3.2; // size by connections
        const disk = new THREE.Sprite(
          new THREE.SpriteMaterial({
            map: diskTexture(),
            color: n.color || "#9fb0d0",
            transparent: true,
            depthWrite: false,
          }),
        );
        disk.scale.set(r, r, 1);
        group.add(disk);
        const label = new SpriteText(n.name);
        label.color = n.color || "#dfe7f5";
        label.textHeight = 2.6 + Math.sqrt(n.val || 1) * 0.5; // bigger for more-connected entities
        label.position.set(0, -(r / 2 + 2.8), 0); // tucked just under the disk
        group.add(label);
        n.__disk = disk;
        n.__label = label;
        return group;
      })
      // Three temporal states, made obvious: just-added (bright white), active (blue),
      // no-longer-active/invalidated (dim red — kept, not deleted). When focusing, non-
      // neighbor edges fade out; in time-view everything shown was active then (blue).
      // Three temporal states: just-added (white), active (blue), no-longer-active (red).
      // Focus dims non-neighbor edges; in time-view everything shown was active then.
      .linkColor((l) => {
        if (hoverNodeRef.current && !highlightLinksRef.current.has(l)) return "rgba(120,130,160,0.05)";
        if (l.timeView) return "rgba(120,200,255,0.6)";
        return l.recent ? "rgba(255,255,255,0.95)" : l.is_current ? "rgba(120,200,255,0.55)" : "rgba(255,90,110,0.26)";
      })
      .linkWidth((l) => {
        const base = l.recent ? 1.7 : l.is_current ? 0.6 : 0.3;
        return hoverNodeRef.current && highlightLinksRef.current.has(l) ? base + 0.9 : base;
      })
      .linkLabel(
        (l) =>
          `<b>${l.name}</b>: ${l.fact}` +
          (l.invalid_at ? ` <span style="color:#ff8da3">· no longer active (${l.invalid_at.slice(0, 10)})</span>` : ""),
      )
      .linkDirectionalArrowLength((l) => (l.is_current || l.timeView ? 3.2 : 1.4))
      .linkDirectionalArrowColor((l) =>
        l.recent ? "#ffffff" : l.is_current || l.timeView ? "rgba(150,200,255,0.7)" : "rgba(255,90,110,0.4)",
      )
      .linkDirectionalArrowRelPos(1)
      // Relationship label on each edge.
      .linkThreeObjectExtend(true)
      .linkThreeObject((l) => {
        const s = new SpriteText((l.name || "").replace(/_/g, " ").toLowerCase());
        s.color = l.recent
          ? "rgba(255,255,255,0.95)"
          : l.is_current || l.timeView
            ? "rgba(206,216,238,0.82)"
            : "rgba(255,140,150,0.5)";
        s.textHeight = l.is_current || l.timeView ? 1.9 : 1.6;
        l.__sprite = s;
        return s;
      })
      .linkPositionUpdate((sprite, { start, end }) => {
        sprite.position.set((start.x + end.x) / 2, (start.y + end.y) / 2, (start.z + end.z) / 2);
      })
      .onNodeHover((node) => {
        if (node === hoverNodeRef.current) return;
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
      })
      .onNodeClick((node) => {
        const d = 90;
        const r = 1 + d / Math.hypot(node.x || 1, node.y || 1, node.z || 1);
        fg.cameraPosition({ x: (node.x || 0) * r, y: (node.y || 0) * r, z: (node.z || 0) * r }, node, 1200);
      });
    fgRef.current = fg;

    // Lighter, snappier camera — the default rotation felt heavy.
    const controls = fg.controls();
    if (controls) {
      controls.rotateSpeed = 2.4;
      controls.zoomSpeed = 1.7;
      controls.panSpeed = 1.2;
      controls.dynamicDampingFactor = 0.35;
    }

    const resize = () => {
      const el = containerRef.current;
      if (el) fg.width(el.clientWidth).height(el.clientHeight);
    };
    resize();
    window.addEventListener("resize", resize);

    loadInitial();
    fetchModels().then(({ models: list }) => setModels(list)).catch(() => {});

    return () => {
      window.removeEventListener("resize", resize);
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
    for (const n of snap.nodes) {
      const ex = byId.get(n.id);
      if (ex) {
        ex.name = n.name;
        ex.summary = n.summary;
      } else {
        byId.set(n.id, { id: n.id, name: n.name, summary: n.summary, labels: n.labels });
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

    // Time range across all dated facts (drives the slider).
    let tmin = Infinity;
    let tmax = Date.now();
    for (const l of snap.links) {
      if (l.valid_at) tmin = Math.min(tmin, Date.parse(l.valid_at));
      if (l.invalid_at) tmax = Math.max(tmax, Date.parse(l.invalid_at));
    }
    if (!isFinite(tmin)) tmin = tmax - 365 * DAY;
    setTimeRange((r) => (r.min === tmin && r.max === tmax ? r : { min: tmin, max: tmax }));

    let links = snap.links.map((l) => ({
      source: l.source,
      target: l.target,
      name: l.name,
      fact: l.fact,
      is_current: l.is_current,
      valid_at: l.valid_at,
      invalid_at: l.invalid_at,
      recent: recentKeysRef.current.has(linkKey(l)),
    }));

    if (timeActiveRef.current) {
      // "As of" view: only facts that were valid at the scrubbed instant.
      const t = asOfRef.current;
      links = links.filter((l) => {
        const v = l.valid_at ? Date.parse(l.valid_at) : -Infinity;
        const iv = l.invalid_at ? Date.parse(l.invalid_at) : Infinity;
        return v <= t && t < iv;
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
    fgRef.current.graphData({ nodes, links });
    setStats(snap.stats);
  }

  // Spotlight the hovered node + neighbors; dim the rest. Node disks/labels are custom
  // objects, so we fade their materials directly; link lines go through the accessors.
  function applyFocus() {
    const hovering = !!hoverNodeRef.current;
    for (const n of nodesRef.current.values()) {
      const on = !hovering || highlightNodesRef.current.has(n);
      if (n.__disk) n.__disk.material.opacity = on ? 1 : 0.1;
      if (n.__label) {
        n.__label.material.transparent = true;
        n.__label.material.opacity = on ? 1 : 0.06;
      }
    }
    for (const l of currentLinksRef.current) {
      if (l.__sprite) {
        l.__sprite.material.transparent = true;
        l.__sprite.material.opacity = !hovering || highlightLinksRef.current.has(l) ? 1 : 0.05;
      }
    }
    const fg = fgRef.current;
    fg.linkColor(fg.linkColor()).linkWidth(fg.linkWidth()); // force link re-evaluation
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
          <button onClick={handleReset} disabled={busy} style={ghostBtn}>
            Reset
          </button>
          <a href={`${window.location.origin}/`} style={{ ...ghostBtn, textDecoration: "none" }}>
            Open chat ↗
          </a>
        </div>
      </div>

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
                {fmtDate(timeActive ? asOf : timeRange.max)}
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
            step={DAY}
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

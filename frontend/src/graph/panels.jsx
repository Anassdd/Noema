// The toolbar popover panels of the graph page: Saves (named checkpoints of the whole
// memory) and Beliefs (the user's own notes per memory context). Pure presenters —
// all state and handlers live in GraphMemoryPage.

import { useState } from "react";

import { ghostBtn, panelAnim, primaryBtn, savesPanel, selectStyle, textareaStyle } from "./styles.js";

export function SavesPanel({
  busy,
  saves,
  open,
  onToggle,
  name,
  onName,
  onSave,
  onRestore,
  onDelete,
  engineTag,
  isAdmin,
}) {
  const [shareAll, setShareAll] = useState(false);
  return (
    <div style={{ position: "relative" }}>
      <button
        onClick={onToggle}
        disabled={busy}
        title={`Named checkpoints of the ${engineTag} memory — saves are per engine`}
        style={ghostBtn}
      >
        ⧉ Saves{saves.length ? ` (${saves.length})` : ""}
      </button>
      <div style={{ ...savesPanel, ...panelAnim(open) }} aria-hidden={!open}>
        <div style={{ fontSize: 11, color: "#7a87a6", marginBottom: 6 }}>
          Save the current {engineTag} memory
        </div>
        <div style={{ display: "flex", gap: 6, marginBottom: isAdmin ? 6 : 10 }}>
          <input
            value={name}
            onChange={(e) => onName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onSave(isAdmin && shareAll)}
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
            onClick={() => onSave(isAdmin && shareAll)}
            disabled={busy || !name.trim()}
            style={{ ...primaryBtn, width: "auto", padding: "5px 12px", opacity: busy || !name.trim() ? 0.5 : 1 }}
          >
            Save
          </button>
        </div>
        {isAdmin && (
          <label
            title="Shared saves appear in every user's memory selector; unshared ones stay yours only"
            style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "#9aa6c2", marginBottom: 10, cursor: "pointer" }}
          >
            <input type="checkbox" checked={shareAll} onChange={(e) => setShareAll(e.target.checked)} />
            share with everyone (admin)
          </label>
        )}
        <div style={{ fontSize: 11, color: "#7a87a6", marginBottom: 4, borderTop: "1px solid rgba(120,135,175,0.15)", paddingTop: 8 }}>
          {engineTag} checkpoints — yours + shared
        </div>
        {saves.length === 0 ? (
          <div style={{ fontSize: 11.5, color: "#6b7693", padding: "4px 0" }}>None yet.</div>
        ) : (
          saves.map((s) => {
            const bench = s.name.startsWith("bench-");
            const deletable = bench || !s.mine ? isAdmin : true;
            const madeBy = (s.engines || [])
              .map((e) => `${e === "graphiti" ? "graph" : e}${s.models?.[e]?.extract ? ` · ${s.models[e].extract}` : ""}`)
              .join("  —  ");
            return (
              <div key={`${s.mine ? "m" : "s"}:${s.name}`} style={{ display: "flex", alignItems: "center", gap: 6, padding: "3px 0" }}>
                <span style={{ flex: 1, minWidth: 0, overflow: "hidden" }}>
                  <span style={{ display: "block", fontSize: 12.5, color: "#e7ecf7", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {s.name}
                  </span>
                  {madeBy && (
                    <span
                      title="Which engine(s) this save holds and the extraction model that created each"
                      style={{ display: "block", fontSize: 9.5, color: "#6b7693", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                    >
                      {madeBy}
                    </span>
                  )}
                </span>
                {bench && (
                  <span
                    title="Benchmark build — frozen test-dataset content, deletable by admins only"
                    style={{ fontSize: 9.5, fontWeight: 600, color: "#ffd166", border: "1px solid rgba(255,209,102,0.4)", background: "rgba(255,209,102,0.1)", borderRadius: 5, padding: "1px 6px" }}
                  >
                    bench
                  </span>
                )}
                <span
                  title={s.mine ? "Visible only to you" : "Shared — visible to every user"}
                  style={{ fontSize: 9.5, fontWeight: 600, borderRadius: 5, padding: "1px 6px",
                           color: s.mine ? "#8fd6c2" : "#9aa6c2",
                           border: `1px solid ${s.mine ? "rgba(143,214,194,0.4)" : "rgba(154,166,194,0.35)"}`,
                           background: s.mine ? "rgba(143,214,194,0.08)" : "rgba(154,166,194,0.08)" }}
                >
                  {s.mine ? "yours" : "shared"}
                </span>
                <button onClick={() => onRestore(s.name)} disabled={busy} style={{ ...ghostBtn, padding: "3px 9px", fontSize: 11.5 }}>
                  Restore
                </button>
                {deletable && (
                  <button
                    onClick={() => onDelete(s.name)}
                    title="Delete this save"
                    style={{ ...ghostBtn, padding: "3px 7px", color: "#ff9db0" }}
                  >
                    ✕
                  </button>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

export function BeliefsPanel({
  busy,
  saves,
  open,
  onToggle,
  context,
  onSelectContext,
  text,
  onText,
  saved,
  onSave,
}) {
  return (
    <div style={{ position: "relative" }}>
      <button onClick={onToggle} disabled={busy} style={ghostBtn}>
        ✎ Beliefs
      </button>
      <div style={{ ...savesPanel, width: 320, ...panelAnim(open) }} aria-hidden={!open}>
        <div style={{ fontSize: 11, color: "#7a87a6", marginBottom: 6 }}>Your own notes for</div>
        <select
          value={context}
          onChange={(e) => onSelectContext(e.target.value)}
          style={{ ...selectStyle, marginBottom: 9 }}
        >
          <option value="">Live memory</option>
          {saves.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <textarea
          value={text}
          onChange={(e) => onText(e.target.value)}
          placeholder="Your own view on this topic — the expert weighs it against the sources and flags disagreements."
          rows={7}
          style={{ ...textareaStyle, marginBottom: 9 }}
        />
        <button onClick={onSave} disabled={busy} style={{ ...primaryBtn, opacity: busy ? 0.5 : 1 }}>
          {saved ? "Saved ✓" : "Save notes"}
        </button>
        <div style={{ fontSize: 10.5, color: "#6b7693", marginTop: 8, lineHeight: 1.5 }}
          title="Beliefs are context notes, not corpus: they are never added to the graph or the vector base.">
          Private notes — never indexed into the memory.
        </div>
      </div>
    </div>
  );
}

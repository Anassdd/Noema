// The toolbar popover panels of the graph page: Saves (named checkpoints of the whole
// memory) and Beliefs (the user's own notes per memory context). Pure presenters —
// all state and handlers live in GraphMemoryPage.

import { ghostBtn, primaryBtn, savesPanel, selectStyle, textareaStyle } from "./styles.js";

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
}) {
  return (
    <div style={{ position: "relative" }}>
      <button onClick={onToggle} disabled={busy} style={ghostBtn}>
        ⧉ Saves{saves.length ? ` (${saves.length})` : ""}
      </button>
      {open && (
        <div style={savesPanel}>
          <div style={{ fontSize: 11, color: "#7a87a6", marginBottom: 6 }}>Save current graph</div>
          <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
            <input
              value={name}
              onChange={(e) => onName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && onSave()}
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
              onClick={onSave}
              disabled={busy || !name.trim()}
              style={{ ...primaryBtn, width: "auto", padding: "5px 12px", opacity: busy || !name.trim() ? 0.5 : 1 }}
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
                <button onClick={() => onRestore(s)} disabled={busy} style={{ ...ghostBtn, padding: "3px 9px", fontSize: 11.5 }}>
                  Restore
                </button>
                <button
                  onClick={() => onDelete(s)}
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
      {open && (
        <div style={{ ...savesPanel, width: 320 }}>
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
            placeholder="What you believe or want the expert to know — e.g. your own view on a topic. When you chat with this memory, answers weigh this against the sources and flag any disagreement."
            rows={7}
            style={{ ...textareaStyle, marginBottom: 9 }}
          />
          <button onClick={onSave} disabled={busy} style={{ ...primaryBtn, opacity: busy ? 0.5 : 1 }}>
            {saved ? "Saved ✓" : "Save notes"}
          </button>
          <div style={{ fontSize: 10.5, color: "#6b7693", marginTop: 8, lineHeight: 1.5 }}>
            Not added to the graph or RAG — kept as your notes and shown to the expert when you chat
            with this memory.
          </div>
        </div>
      )}
    </div>
  );
}

// Shared inline styles for the graph page and its panels — one dark glassy language.

export const ghostBtn = {
  background: "rgba(120,135,175,0.12)",
  border: "1px solid rgba(120,135,175,0.22)",
  color: "#cdd5ea",
  fontSize: 12.5,
  fontWeight: 500,
  padding: "5px 11px",
  borderRadius: 8,
  cursor: "pointer",
};

export const selectStyle = {
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

export const textareaStyle = {
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

export const uploadBtn = {
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

export const primaryBtn = {
  width: "100%",
  background: "#3f6fe0",
  border: "1px solid rgba(255,255,255,0.14)",
  color: "#ffffff",
  fontSize: 13,
  fontWeight: 650,
  padding: "9px 0",
  borderRadius: 9,
  cursor: "pointer",
};

export const savesPanel = {
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

// Keeps a popover mounted in both states so it eases in AND out (a conditionally
// rendered panel unmounts instantly on close, skipping any exit motion).
export function panelAnim(open) {
  return {
    opacity: open ? 1 : 0,
    transform: open ? "translateY(0) scale(1)" : "translateY(-8px) scale(0.98)",
    transformOrigin: "top right",
    pointerEvents: open ? "auto" : "none",
    transition: "opacity 0.16s ease, transform 0.18s cubic-bezier(0.22, 1, 0.36, 1)",
  };
}

export const viewToolbar = {
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

export const leftPanel = {
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

export const timeBar = {
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

export const spinner = {
  width: 11,
  height: 11,
  border: "2px solid rgba(143,214,194,0.35)",
  borderTopColor: "#8fd6c2",
  borderRadius: "50%",
  display: "inline-block",
  animation: "spin 0.7s linear infinite",
};

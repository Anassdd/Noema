// Bench-page inline styles — themed via the app's CSS variables (the graph page
// keeps its own fixed dark language in graph/styles.js).

export const ghostBtn = {
  background: "var(--row-hover)",
  border: "1px solid var(--border)",
  color: "var(--text-soft)",
  fontSize: 12.5,
  fontWeight: 500,
  padding: "5px 11px",
  borderRadius: 8,
  cursor: "pointer",
};

export const selectStyle = {
  width: "100%",
  background: "var(--row-active)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  padding: "6px 8px",
  color: "var(--text)",
  fontSize: 12,
  outline: "none",
  cursor: "pointer",
};

export const primaryBtn = {
  width: "100%",
  background: "var(--accent)",
  border: "none",
  color: "#ffffff",
  fontSize: 13,
  fontWeight: 700,
  padding: "9px 0",
  borderRadius: 9,
  cursor: "pointer",
};

export const spinner = {
  width: 11,
  height: 11,
  border: "2px solid color-mix(in srgb, var(--ok) 35%, transparent)",
  borderTopColor: "var(--ok)",
  borderRadius: "50%",
  display: "inline-block",
  animation: "spin 0.7s linear infinite",
};

import { StrictMode, Suspense, lazy } from "react";
import { createRoot } from "react-dom/client";

import App from "./App.jsx";
import "./index.css";

// One app, two surfaces opened in separate browser tabs: the chat (default) and
// the graph-memory page (?view=graph). The graph page pulls in three.js, so it's
// lazy-loaded — the chat bundle stays light and only pays for it when opened.
const GraphMemoryPage = lazy(() => import("./graph/GraphMemoryPage.jsx"));
const view = new URLSearchParams(window.location.search).get("view");

createRoot(document.getElementById("root")).render(
  <StrictMode>
    {view === "graph" ? (
      <Suspense fallback={<div style={{ background: "#070912", position: "fixed", inset: 0 }} />}>
        <GraphMemoryPage />
      </Suspense>
    ) : (
      <App />
    )}
  </StrictMode>,
);

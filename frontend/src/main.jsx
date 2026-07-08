import { StrictMode, Suspense, lazy } from "react";
import { createRoot } from "react-dom/client";

import App from "./App.jsx";
import "./index.css";

// One app, three surfaces opened in separate browser tabs: the chat (default),
// the graph-memory page (?view=graph) and the bench (?view=bench). The extra pages
// are lazy-loaded — the chat bundle stays light and only pays for them when opened.
const GraphMemoryPage = lazy(() => import("./graph/GraphMemoryPage.jsx"));
const BenchPage = lazy(() => import("./bench/BenchPage.jsx"));
const view = new URLSearchParams(window.location.search).get("view");
const dark = <div style={{ background: "#070912", position: "fixed", inset: 0 }} />;

createRoot(document.getElementById("root")).render(
  <StrictMode>
    {view === "graph" ? (
      <Suspense fallback={dark}>
        <GraphMemoryPage />
      </Suspense>
    ) : view === "bench" ? (
      <Suspense fallback={dark}>
        <BenchPage />
      </Suspense>
    ) : (
      <App />
    )}
  </StrictMode>,
);

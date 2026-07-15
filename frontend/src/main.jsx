import { StrictMode, Suspense, lazy, useState } from "react";
import { createRoot } from "react-dom/client";

import App from "./App.jsx";
import AuthPage from "./components/AuthPage.jsx";
import { getSession } from "./api/client.js";
import { applySavedTheme } from "./lib/theme.js";
import "./index.css";

applySavedTheme();

// One app, three surfaces opened in separate browser tabs: the chat (default),
// the graph-memory page (?view=graph) and the bench (?view=bench). The extra pages
// are lazy-loaded — the chat bundle stays light and only pays for them when opened.
// All of them sit behind the auth gate: no session, no app.
const GraphMemoryPage = lazy(() => import("./graph/GraphMemoryPage.jsx"));
const BenchPage = lazy(() => import("./bench/BenchPage.jsx"));
const view = new URLSearchParams(window.location.search).get("view");
const dark = <div style={{ background: "#070912", position: "fixed", inset: 0 }} />;

function Root() {
  const [session, setSession] = useState(getSession);
  if (!session) return <AuthPage onAuthed={setSession} />;
  if (view === "graph") {
    return (
      <Suspense fallback={dark}>
        <GraphMemoryPage />
      </Suspense>
    );
  }
  if (view === "bench") {
    return (
      <Suspense fallback={dark}>
        <BenchPage />
      </Suspense>
    );
  }
  return <App />;
}

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);

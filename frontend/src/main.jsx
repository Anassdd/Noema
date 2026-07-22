import { StrictMode, Suspense, lazy, useState } from "react";
import { createRoot } from "react-dom/client";

import App from "./App.jsx";
import AuthPage from "./components/AuthPage.jsx";
import { getSession } from "./api/client.js";
import { applySavedTheme } from "./lib/theme.js";
import "./index.css";

applySavedTheme();

// One app, five surfaces opened in separate browser tabs: the chat (default),
// the graph-memory page (?view=graph), the personal-memory page (?view=memory),
// the bench (?view=bench) and the admin page (?view=admin). The extra pages are
// lazy-loaded — the chat bundle stays light and only pays for them when opened.
// All of them sit behind the auth gate: no session, no app. Bench and admin
// additionally require an admin account (backend-enforced).
const GraphMemoryPage = lazy(() => import("./graph/GraphMemoryPage.jsx"));
const MemoryPage = lazy(() => import("./memory/MemoryPage.jsx"));
const BenchPage = lazy(() => import("./bench/BenchPage.jsx"));
const AdminPage = lazy(() => import("./admin/AdminPage.jsx"));
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
  if (view === "memory") {
    return (
      <Suspense fallback={dark}>
        <MemoryPage />
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
  if (view === "admin") {
    return (
      <Suspense fallback={dark}>
        <AdminPage />
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

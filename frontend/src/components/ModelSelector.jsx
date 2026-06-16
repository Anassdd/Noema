import { useState } from "react";

// Dropdown to pick the chat model. Includes a search box since the endpoint can
// expose many models. Closes on outside click or selection.
export default function ModelSelector({ models, value, onChange, onReload }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  const filtered = query
    ? models.filter((m) => m.toLowerCase().includes(query.toLowerCase()))
    : models;

  const choose = (m) => {
    onChange(m);
    setOpen(false);
    setQuery("");
  };

  const toggle = () => {
    // Self-heal: if the initial fetch failed (e.g. backend was restarting),
    // opening an empty selector retries it.
    if (!open && models.length === 0) onReload?.();
    setOpen((o) => !o);
  };

  return (
    <div className="relative">
      <button
        onClick={toggle}
        className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm font-medium text-zinc-700 transition hover:bg-zinc-100 dark:text-zinc-200 dark:hover:bg-white/10"
      >
        <span className="max-w-[200px] truncate">{value || "Select model"}</span>
        <svg
          className={`h-4 w-4 text-zinc-400 transition-transform ${open ? "rotate-180" : ""}`}
          viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          <div className="animate-pop-in absolute left-0 z-40 mt-1 w-72 rounded-xl border border-zinc-200 bg-white p-1.5 shadow-lg dark:border-white/10 dark:bg-zinc-900">
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search models…"
              className="mb-1.5 w-full rounded-lg border border-zinc-200 px-2.5 py-1.5 text-sm text-zinc-800 placeholder-zinc-400 outline-none focus:border-zinc-300 dark:border-white/10 dark:bg-zinc-800 dark:text-zinc-100 dark:placeholder-zinc-500"
            />
            <div className="max-h-64 overflow-y-auto">
              {filtered.length === 0 ? (
                <p className="px-3 py-2 text-sm text-zinc-400">No models found.</p>
              ) : (
                filtered.map((m) => (
                  <button
                    key={m}
                    onClick={() => choose(m)}
                    className={`flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-sm transition ${
                      m === value
                        ? "bg-zinc-100 font-medium text-zinc-900 dark:bg-white/10 dark:text-zinc-100"
                        : "text-zinc-700 hover:bg-zinc-50 dark:text-zinc-300 dark:hover:bg-white/5"
                    }`}
                  >
                    <span className="truncate">{m}</span>
                    {m === value && (
                      <svg className="h-4 w-4 shrink-0 text-indigo-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M20 6L9 17l-5-5" />
                      </svg>
                    )}
                  </button>
                ))
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

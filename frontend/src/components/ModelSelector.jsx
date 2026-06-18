import { useState } from "react";

import { ChevronDownIcon, CheckIcon } from "./icons.jsx";

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
    // Self-heal: opening an empty selector retries the fetch.
    if (!open && models.length === 0) onReload?.();
    setOpen((o) => !o);
  };

  return (
    <div className="relative">
      <button
        onClick={toggle}
        className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 font-mono text-[11px] transition hover:bg-[var(--row-hover)]"
        style={{ color: "var(--accent)" }}
      >
        <span className="max-w-[180px] truncate">{value || "Select model"}</span>
        <span style={{ color: "var(--text-faint)" }} className={open ? "rotate-180" : ""}>
          <ChevronDownIcon size={13} sw={2} />
        </span>
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          <div
            className="animate-pop-in absolute right-0 z-40 mt-1 w-72 rounded-xl border p-1.5"
            style={{ background: "var(--sidebar-bg)", borderColor: "var(--border)", boxShadow: "var(--win-shadow)" }}
          >
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search models…"
              className="mb-1.5 w-full rounded-lg border px-2.5 py-1.5 text-sm outline-none"
              style={{ borderColor: "var(--border)", background: "transparent", color: "var(--text)" }}
            />
            <div className="max-h-64 overflow-y-auto">
              {filtered.length === 0 ? (
                <p className="px-3 py-2 text-sm" style={{ color: "var(--text-faint)" }}>
                  No models found.
                </p>
              ) : (
                filtered.map((m) => (
                  <button
                    key={m}
                    onClick={() => choose(m)}
                    className="flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-sm transition hover:bg-[var(--row-hover)]"
                    style={
                      m === value
                        ? { background: "var(--row-active)", color: "var(--text)", fontWeight: 500 }
                        : { color: "var(--text-soft)" }
                    }
                  >
                    <span className="truncate">{m}</span>
                    {m === value && (
                      <span style={{ color: "var(--accent)" }}>
                        <CheckIcon size={15} sw={2.5} />
                      </span>
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

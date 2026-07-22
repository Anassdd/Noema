import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { clearMemory, fetchMemory, saveMemoryFile } from "../api/memory.js";
import { MoonIcon, SunIcon } from "../components/icons.jsx";
import { applyTheme, onThemeChange, savedDarkMode, savedThemeFamily } from "../lib/theme.js";

// Standalone memory surface (?view=memory), opened in its own tab like the
// graph and bench pages. Same shell as the chat app — wallpaper + glass panel,
// theme variables, shared dark-mode setting. Left rail: the four files with
// live gauges; main area: a full-height editor.
const FILES = [
  {
    name: "profile",
    label: "Profile",
    desc: "Topic sections of connected prose. Always in context.",
  },
  {
    name: "now",
    label: "Now",
    desc: "Current, time-bound facts with end dates. Always in context.",
  },
  {
    name: "history",
    label: "History",
    desc: "Retired facts with their date ranges. Searched on demand.",
  },
  {
    name: "journal",
    label: "Journal",
    desc: "One line per chat per day — recent tail in context, rest searched on demand.",
  },
];

const SECTION_RE = /^##\s+(.+?)(?:\s*\(\d{4}-\d{2}-\d{2}\))?\s*$/gm;

// Same look as the chat header's icon buttons.
function HeaderButton({ label, onClick, disabled, children }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      className="grid h-8 w-8 place-items-center rounded-[9px] border transition disabled:opacity-50"
      style={{ borderColor: "var(--border)", color: "var(--text-soft)" }}
    >
      {children}
    </button>
  );
}

const RefreshIcon = ({ size = 15 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 12a9 9 0 1 1-2.64-6.36" />
    <path d="M21 3v6h-6" />
  </svg>
);

export default function MemoryPage() {
  const [state, setState] = useState(null); // {files, usage, ...}
  const [drafts, setDrafts] = useState(null);
  const [tab, setTab] = useState("profile");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [theme, setTheme] = useState(() => ({
    dark: savedDarkMode(),
    family: savedThemeFamily(),
  }));
  const [toast, setToast] = useState("");
  const toastTimer = useRef(null);

  // Same appearance as the chat: apply the shared setting, follow live changes
  // made in the chat tab, and write ours back for it to follow.
  useEffect(() => {
    applyTheme(theme.dark, theme.family);
  }, [theme]);
  useEffect(() => onThemeChange((dark, family) => setTheme({ dark, family })), []);
  useEffect(() => () => clearTimeout(toastTimer.current), []);

  const flash = (message) => {
    setToast(message);
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(""), 1800);
  };

  const load = useCallback(async (note) => {
    setBusy(true);
    setError("");
    try {
      const s = await fetchMemory();
      setState(s);
      setDrafts({ ...s.files });
      if (note) flash(note);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const anyDirty = drafts && state && FILES.some((f) => drafts[f.name] !== state.files[f.name]);
  const refresh = () => {
    if (anyDirty && !window.confirm("Discard unsaved edits and reload?")) return;
    load("Refreshed");
  };

  const save = useCallback(async () => {
    if (!drafts) return;
    setBusy(true);
    setError("");
    try {
      const next = await saveMemoryFile(tab, drafts[tab] ?? "");
      setState(next);
      setDrafts((d) => ({ ...d, [tab]: next.files[tab] }));
      flash(`Saved ${tab}.md`);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }, [drafts, tab]);

  // Cmd/Ctrl+S saves the open file instead of the browser dialog.
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "s") {
        e.preventDefault();
        save();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [save]);

  const wipe = async () => {
    if (!window.confirm("Clear ALL memory — profile, now, history and journal? This can't be undone.")) return;
    setBusy(true);
    try {
      const next = await clearMemory();
      setState(next);
      setDrafts({ ...next.files });
      flash("Memory cleared");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const dirty = (name) => drafts && state && drafts[name] !== state.files[name];
  const topics = useMemo(
    () => [...(drafts?.profile ?? "").matchAll(SECTION_RE)].map((m) => m[1]),
    [drafts],
  );
  const gauge = state?.usage?.[tab];
  const chars = (drafts?.[tab] ?? "").length;

  return (
    <div className="app-bg flex h-full w-full overflow-hidden">
      <main
        className="glass-panel relative flex min-w-0 flex-1 flex-col"
        style={{ color: "var(--text)" }}
      >
        <header
          className="flex h-14 flex-shrink-0 items-center gap-3 border-b px-5"
          style={{ borderColor: "var(--border-soft)" }}
        >
          <div
            className="font-serif truncate text-[17px]"
            style={{ fontWeight: "var(--title-weight)" }}
          >
            Memory
          </div>
          <span className="text-[12.5px]" style={{ color: "var(--text-faint)" }}>
            what the assistant knows about you
          </span>
          <div className="ml-auto flex items-center gap-2">
            <HeaderButton label="Refresh" onClick={refresh} disabled={busy}>
              <RefreshIcon />
            </HeaderButton>
            <HeaderButton
              label={theme.dark ? "Light mode" : "Dark mode"}
              onClick={() => setTheme((t) => ({ ...t, dark: !t.dark }))}
            >
              {theme.dark ? <SunIcon size={16} /> : <MoonIcon size={16} />}
            </HeaderButton>
            <button
              onClick={wipe}
              disabled={busy}
              className="rounded-lg border px-3 py-1.5 text-[12.5px] font-medium transition disabled:opacity-50"
              style={{ borderColor: "var(--danger)", color: "var(--danger)" }}
            >
              Clear all
            </button>
          </div>
        </header>

        {toast && (
          <div
            className="animate-fade-in absolute left-1/2 top-16 z-20 -translate-x-1/2 rounded-full border px-4 py-1.5 text-[12.5px] font-medium shadow-lg"
            style={{
              background: "var(--sidebar-bg)",
              borderColor: "var(--accent-border)",
              color: "var(--accent)",
            }}
          >
            {toast}
          </div>
        )}

        {error && (
          <p className="px-5 py-2 text-xs" style={{ color: "var(--danger)" }}>
            {error}
          </p>
        )}

        <div className="flex min-h-0 flex-1">
          <aside className="flex w-72 shrink-0 flex-col gap-3 overflow-y-auto p-5">
            {FILES.map((f) => {
              const u = state?.usage?.[f.name];
              const len = (drafts?.[f.name] ?? "").length;
              const active = tab === f.name;
              return (
                <button
                  key={f.name}
                  onClick={() => setTab(f.name)}
                  className="rounded-xl border p-4 text-left transition"
                  style={{
                    background: active ? "var(--row-active)" : "transparent",
                    borderColor: active ? "var(--accent-border)" : "var(--border)",
                  }}
                >
                  <div className="flex items-baseline justify-between">
                    <span
                      className="text-[14px] font-semibold"
                      style={{ color: active ? "var(--accent)" : "var(--text)" }}
                    >
                      {f.label}
                      {dirty(f.name) && (
                        <span title="Unsaved changes" style={{ color: "var(--accent)" }}> •</span>
                      )}
                    </span>
                    <span className="font-mono text-[10.5px]" style={{ color: "var(--text-faint)" }}>
                      {u ? `${len}/${u.cap}` : `${len} chars`}
                    </span>
                  </div>
                  <p className="mt-1 text-[11.5px] leading-snug" style={{ color: "var(--text-soft)" }}>
                    {f.desc}
                  </p>
                  {u && (
                    <div
                      className="mt-2.5 h-1 overflow-hidden rounded-full"
                      style={{ background: "var(--row-hover)" }}
                    >
                      <div
                        className="h-full rounded-full transition-all"
                        style={{
                          width: `${Math.min(100, (len / u.cap) * 100)}%`,
                          background: len > u.cap ? "var(--danger)" : "var(--accent)",
                        }}
                      />
                    </div>
                  )}
                </button>
              );
            })}

            {topics.length > 0 && (
              <div className="mt-1 px-1">
                <div
                  className="mb-1.5 text-[10.5px] font-medium uppercase"
                  style={{ letterSpacing: ".06em", color: "var(--text-faint)" }}
                >
                  Profile topics
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {topics.map((t) => (
                    <span
                      key={t}
                      className="rounded-full border px-2.5 py-0.5 text-[11px]"
                      style={{ borderColor: "var(--border)", color: "var(--text-soft)" }}
                    >
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </aside>

          <div className="flex min-w-0 flex-1 flex-col p-5 pl-0">
            <div
              className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border"
              style={{ borderColor: "var(--border)" }}
            >
              <textarea
                value={drafts?.[tab] ?? ""}
                onChange={(e) => setDrafts((d) => ({ ...d, [tab]: e.target.value }))}
                disabled={busy || !drafts}
                spellCheck={false}
                placeholder={
                  {
                    profile: "## Topic (YYYY-MM-DD)\nConnected prose about you…",
                    now: "One dated fact per line — fact (learned → until)…",
                    history: "Retired facts land here automatically…",
                    journal: "One dated line per conversation, written daily…",
                  }[tab]
                }
                className="min-h-0 flex-1 resize-none bg-transparent p-5 font-mono text-[13px] leading-relaxed outline-none"
                style={{ color: "var(--text)" }}
              />
              <div
                className="flex items-center gap-3 px-5 py-3"
                style={{ borderTop: "1px solid var(--border-soft)" }}
              >
                <span className="text-[11.5px]" style={{ color: "var(--text-faint)" }}>
                  {FILES.find((f) => f.name === tab)?.desc}
                </span>
                <span
                  className="ml-auto font-mono text-[11px]"
                  style={{ color: gauge && chars > gauge.cap ? "var(--danger)" : "var(--text-faint)" }}
                >
                  {gauge ? `${chars}/${gauge.cap}` : `${chars} chars`}
                </span>
                <button
                  onClick={save}
                  disabled={busy || !dirty(tab)}
                  className="rounded-lg px-4 py-1.5 text-[12.5px] font-medium transition disabled:opacity-50"
                  style={{ background: "var(--send-bg)", color: "var(--send-fg)" }}
                >
                  {dirty(tab) ? "Save  ⌘S" : "Saved"}
                </button>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

import { useState } from "react";

import Toggle from "./Toggle.jsx";
import { CheckIcon, CloseIcon } from "./icons.jsx";

// Each card shows a tiny live preview (wallpaper + a wordmark in the family's
// heading font) so the serif-vs-grotesque difference is visible before you pick.
const THEMES = [
  {
    id: "aurora",
    name: "Aurora",
    desc: "Serif · gradient glass",
    bg: "linear-gradient(138deg,#2a44d8,#5f67ee,#a294f3)",
    chip: "rgba(255,255,255,0.82)",
    ink: "#1f1f22",
    font: "'Newsreader', Georgia, serif",
    tracking: ".12em",
    accent: "#2f6bff",
  },
  {
    id: "codex",
    name: "Codex",
    desc: "Geist · flat & solid",
    bg: "#15171d",
    chip: null,
    ink: "#f0f1f4",
    font: "'Geist', system-ui, sans-serif",
    tracking: "-.01em",
    accent: "#5b8cff",
  },
];

// Centered modal holding appearance + feature toggles + the clear-memory action.
// Click the backdrop or the × to close.
export default function SettingsModal({
  memoryEnabled,
  onToggleMemory,
  prefilterEnabled,
  onTogglePrefilter,
  tokenizerEnabled,
  onToggleTokenizer,
  darkMode,
  onToggleDarkMode,
  themeFamily,
  onApplyTheme,
  memoryCount,
  onClearMemory,
  onClose,
}) {
  const [pendingTheme, setPendingTheme] = useState(themeFamily);
  const dirty = pendingTheme !== themeFamily;

  return (
    <div
      className="animate-fade-in fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="animate-pop-in w-full max-w-md overflow-hidden rounded-2xl"
        style={{
          background: "var(--sidebar-bg)",
          border: "1px solid var(--border)",
          boxShadow: "var(--win-shadow)",
          color: "var(--text)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 pt-5">
          <h2 className="text-base font-semibold">Settings</h2>
          <button
            onClick={onClose}
            aria-label="Close settings"
            className="grid h-7 w-7 place-items-center rounded-lg transition hover:bg-[var(--row-hover)]"
            style={{ color: "var(--text-faint)" }}
          >
            <CloseIcon size={16} />
          </button>
        </div>

        <div className="px-5 py-4">
          <SectionLabel>Theme</SectionLabel>
          <div className="grid grid-cols-2 gap-3">
            {THEMES.map((t) => (
              <ThemeCard
                key={t.id}
                theme={t}
                selected={pendingTheme === t.id}
                onSelect={() => setPendingTheme(t.id)}
              />
            ))}
          </div>
          <button
            onClick={() => dirty && onApplyTheme(pendingTheme)}
            disabled={!dirty}
            className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-lg py-2 text-sm font-medium transition disabled:cursor-default"
            style={{
              background: dirty ? "var(--send-bg)" : "var(--row-active)",
              color: dirty ? "var(--send-fg)" : "var(--text-faint)",
            }}
          >
            {dirty ? (
              "Confirm theme"
            ) : (
              <>
                <CheckIcon size={14} sw={2.4} />
                Theme applied
              </>
            )}
          </button>
        </div>

        <div className="px-5 pb-1" style={{ borderTop: "1px solid var(--border-soft)" }}>
          <SettingRow
            title="Dark mode"
            desc="Switch the interface to a dark theme."
            control={<Toggle on={darkMode} onClick={onToggleDarkMode} label="Toggle dark mode" />}
          />
          <SettingRow
            title="Memory"
            desc="Save facts across chats and feed them back into the bot."
            control={<Toggle on={memoryEnabled} onClick={onToggleMemory} label="Toggle memory" />}
          />
          <SettingRow
            title="Auto-capture pre-filter"
            desc="Only run the memory judge on fact-like messages. Off = judge every turn (more calls)."
            disabled={!memoryEnabled}
            control={
              <Toggle
                on={prefilterEnabled}
                onClick={onTogglePrefilter}
                disabled={!memoryEnabled}
                label="Toggle memory pre-filter"
              />
            }
          />
          <SettingRow
            title="Live token estimate"
            desc="Show your message's exact token count while typing."
            control={
              <Toggle on={tokenizerEnabled} onClick={onToggleTokenizer} label="Toggle live token estimate" />
            }
          />
        </div>

        <div className="px-5 pb-5 pt-4">
          <button
            onClick={onClearMemory}
            disabled={!memoryCount}
            className="w-full rounded-lg border px-3 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50"
            style={{ borderColor: "var(--danger)", color: "var(--danger)" }}
          >
            Clear memory
          </button>
        </div>
      </div>
    </div>
  );
}

function ThemeCard({ theme, selected, onSelect }) {
  return (
    <button
      onClick={onSelect}
      className="overflow-hidden rounded-xl border text-left transition"
      style={{
        borderColor: selected ? "var(--accent)" : "var(--border)",
        boxShadow: selected ? "0 0 0 1px var(--accent)" : "none",
      }}
    >
      <div className="grid h-[68px] place-items-center" style={{ background: theme.bg }}>
        <div
          className="flex items-center gap-1.5 rounded-lg px-3 py-1.5"
          style={theme.chip ? { background: theme.chip, boxShadow: "0 2px 8px rgba(20,28,80,0.18)" } : undefined}
        >
          <span
            style={{ fontFamily: theme.font, letterSpacing: theme.tracking, color: theme.ink, fontSize: 14, fontWeight: 600 }}
          >
            Noema
          </span>
          <span className="h-1.5 w-1.5 rounded-full" style={{ background: theme.accent }} />
        </div>
      </div>
      <div className="px-2.5 py-2" style={{ background: "var(--panel-bg)" }}>
        <div className="flex items-center gap-1.5 text-[13px] font-medium" style={{ color: "var(--text)" }}>
          {theme.name}
          {selected && <CheckIcon size={13} sw={2.6} />}
        </div>
        <div className="text-[11px]" style={{ color: "var(--text-faint)" }}>
          {theme.desc}
        </div>
      </div>
    </button>
  );
}

function SectionLabel({ children }) {
  return (
    <div className="mb-2 text-[11px] font-medium uppercase" style={{ letterSpacing: ".06em", color: "var(--text-faint)" }}>
      {children}
    </div>
  );
}

function SettingRow({ title, desc, control, disabled }) {
  return (
    <div className={`flex items-center justify-between gap-4 py-3 ${disabled ? "opacity-50" : ""}`}>
      <div className="min-w-0">
        <div className="text-sm font-medium" style={{ color: "var(--text)" }}>
          {title}
        </div>
        <div className="text-xs" style={{ color: "var(--text-soft)" }}>
          {desc}
        </div>
      </div>
      {control}
    </div>
  );
}

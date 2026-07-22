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

// Settings: a larger two-pane modal — section nav on the left, one section's
// controls on the right. Click the backdrop or the × to close.
export default function SettingsModal({
  memoryEnabled,
  onToggleMemory,
  expertEnabled,
  onToggleExpert,
  prefilterEnabled,
  onTogglePrefilter,
  tokenizerEnabled,
  onToggleTokenizer,
  darkMode,
  onToggleDarkMode,
  themeFamily,
  onApplyTheme,
  prodMode,
  onToggleProdMode,
  memoryCount,
  onClearMemory,
  onEditMemoryFiles,
  isAdmin,
  onOpenAdmin,
  onClose,
}) {
  const [section, setSection] = useState("appearance");
  const [pendingTheme, setPendingTheme] = useState(themeFamily);
  const themeDirty = pendingTheme !== themeFamily;

  const sections = [
    { id: "appearance", label: "Appearance" },
    { id: "chat", label: "Chat" },
    { id: "memory", label: "Memory" },
    { id: "application", label: "Application" },
    ...(isAdmin ? [{ id: "admin", label: "Administration" }] : []),
  ];

  return (
    <div
      className="animate-fade-in fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="animate-pop-in flex h-[540px] w-full max-w-3xl overflow-hidden rounded-2xl"
        style={{
          background: "var(--sidebar-bg)",
          border: "1px solid var(--border)",
          boxShadow: "var(--win-shadow)",
          color: "var(--text)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <aside
          className="flex w-52 shrink-0 flex-col gap-1 p-4"
          style={{ borderRight: "1px solid var(--border-soft)" }}
        >
          <div className="px-2 pb-3 pt-1 text-base font-semibold">Settings</div>
          {sections.map((s) => (
            <button
              key={s.id}
              onClick={() => setSection(s.id)}
              className="rounded-lg px-3 py-2 text-left text-[13.5px] font-medium transition"
              style={{
                background: section === s.id ? "var(--row-active)" : "transparent",
                color: section === s.id ? "var(--text)" : "var(--text-soft)",
              }}
            >
              {s.label}
            </button>
          ))}
        </aside>

        <div className="flex min-w-0 flex-1 flex-col" style={{ background: "var(--panel-bg)" }}>
          <div className="flex items-center justify-between px-6 pt-5">
            <h2 className="text-[15px] font-semibold">
              {sections.find((s) => s.id === section)?.label}
            </h2>
            <button
              onClick={onClose}
              aria-label="Close settings"
              className="grid h-7 w-7 place-items-center rounded-lg transition hover:bg-[var(--row-hover)]"
              style={{ color: "var(--text-faint)" }}
            >
              <CloseIcon size={16} />
            </button>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
            {section === "appearance" && (
              <>
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
                  onClick={() => themeDirty && onApplyTheme(pendingTheme)}
                  disabled={!themeDirty}
                  className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-lg py-2 text-sm font-medium transition disabled:cursor-default"
                  style={{
                    background: themeDirty ? "var(--send-bg)" : "var(--row-active)",
                    color: themeDirty ? "var(--send-fg)" : "var(--text-faint)",
                  }}
                >
                  {themeDirty ? (
                    "Confirm theme"
                  ) : (
                    <>
                      <CheckIcon size={14} sw={2.4} />
                      Theme applied
                    </>
                  )}
                </button>
                <div className="mt-2">
                  <SettingRow
                    title="Dark mode"
                    desc="Switch the interface to a dark theme."
                    control={<Toggle on={darkMode} onClick={onToggleDarkMode} label="Toggle dark mode" />}
                  />
                </div>
              </>
            )}

            {section === "chat" && (
              <>
                <SettingRow
                  title="Expert mode"
                  desc="Ground answers in your uploaded documents (retrieve → verify → cite). Off = plain chat."
                  control={<Toggle on={expertEnabled} onClick={onToggleExpert} label="Toggle expert mode" />}
                />
                <SettingRow
                  title="Live token estimate"
                  desc="Show your message's exact token count while typing. Hidden in production mode."
                  control={
                    <Toggle on={tokenizerEnabled} onClick={onToggleTokenizer} label="Toggle live token estimate" />
                  }
                />
              </>
            )}

            {section === "memory" && (
              <>
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
                  title="Memory files"
                  desc="Profile · Now · History · Journal — the hand-editable markdown files behind memory."
                  disabled={!memoryEnabled}
                  control={
                    <button
                      onClick={onEditMemoryFiles}
                      disabled={!memoryEnabled}
                      className="whitespace-nowrap rounded-lg border px-3 py-1.5 text-[12.5px] font-medium transition hover:bg-[var(--row-hover)] disabled:cursor-not-allowed"
                      style={{ borderColor: "var(--accent-border)", color: "var(--accent)" }}
                    >
                      Edit ↗
                    </button>
                  }
                />
                <SettingRow
                  title="Clear memory"
                  desc="Wipe all four memory files. This can't be undone."
                  control={
                    <button
                      onClick={onClearMemory}
                      disabled={!memoryCount}
                      className="whitespace-nowrap rounded-lg border px-3 py-1.5 text-[12.5px] font-medium transition disabled:cursor-not-allowed disabled:opacity-50"
                      style={{ borderColor: "var(--danger)", color: "var(--danger)" }}
                    >
                      Clear
                    </button>
                  }
                />
              </>
            )}

            {section === "application" && (
              <SettingRow
                title="Production mode"
                desc="Clean end-user app: hides the token metrics (per-answer breakdown, session meter, live estimate). The runtime trace and the model picker stay."
                control={<Toggle on={prodMode} onClick={onToggleProdMode} label="Toggle production mode" />}
              />
            )}

            {section === "admin" && isAdmin && (
              <SettingRow
                title="Administration"
                desc="Manage accounts: rename, reset passwords, admin rights, delete."
                control={
                  <button
                    onClick={onOpenAdmin}
                    className="whitespace-nowrap rounded-lg border px-3 py-1.5 text-[12.5px] font-medium transition hover:bg-[var(--row-hover)]"
                    style={{ borderColor: "var(--accent-border)", color: "var(--accent)" }}
                  >
                    Manage ↗
                  </button>
                }
              />
            )}
          </div>
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
    <div
      className={`flex items-center justify-between gap-4 py-3.5 ${disabled ? "opacity-50" : ""}`}
      style={{ borderBottom: "1px solid var(--border-soft)" }}
    >
      <div className="min-w-0">
        <div className="text-sm font-medium" style={{ color: "var(--text)" }}>
          {title}
        </div>
        <div className="mt-0.5 text-xs leading-relaxed" style={{ color: "var(--text-soft)" }}>
          {desc}
        </div>
      </div>
      {control}
    </div>
  );
}

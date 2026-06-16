import Toggle from "./Toggle.jsx";

// Centered modal holding the app's feature toggles + the clear-memory action.
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
  memoryCount,
  onClearMemory,
  onClose,
}) {
  return (
    <div
      className="animate-fade-in fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="animate-pop-in w-full max-w-md rounded-2xl bg-white p-5 shadow-xl dark:bg-zinc-900"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-zinc-800 dark:text-zinc-100">Settings</h2>
          <button
            onClick={onClose}
            aria-label="Close settings"
            className="grid h-7 w-7 place-items-center rounded-lg text-zinc-400 transition hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-white/10 dark:hover:text-zinc-200"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>

        <div className="mt-4 divide-y divide-zinc-100 dark:divide-white/10">
          <SettingRow
            title="Memory"
            desc="Save facts across chats and feed them back into the bot."
            control={
              <Toggle
                on={memoryEnabled}
                onClick={onToggleMemory}
                label="Toggle memory"
              />
            }
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
              <Toggle
                on={tokenizerEnabled}
                onClick={onToggleTokenizer}
                label="Toggle live token estimate"
              />
            }
          />
          <SettingRow
            title="Dark mode"
            desc="Switch the interface to a dark theme."
            control={
              <Toggle
                on={darkMode}
                onClick={onToggleDarkMode}
                label="Toggle dark mode"
              />
            }
          />
        </div>

        <div className="mt-5 border-t border-zinc-200 pt-4 dark:border-white/10">
          <button
            onClick={onClearMemory}
            disabled={!memoryCount}
            className="w-full rounded-lg border border-red-200 px-3 py-2 text-sm font-medium text-red-600 transition hover:bg-red-50 disabled:cursor-not-allowed disabled:border-zinc-200 disabled:text-zinc-400 disabled:hover:bg-transparent dark:border-red-900 dark:text-red-400 dark:hover:bg-red-950/40 dark:disabled:border-white/10 dark:disabled:text-zinc-600"
          >
            Clear memory
          </button>
        </div>
      </div>
    </div>
  );
}

function SettingRow({ title, desc, control, disabled }) {
  return (
    <div
      className={`flex items-center justify-between gap-4 py-3 ${
        disabled ? "opacity-50" : ""
      }`}
    >
      <div className="min-w-0">
        <div className="text-sm font-medium text-zinc-800 dark:text-zinc-100">{title}</div>
        <div className="text-xs text-zinc-500 dark:text-zinc-400">{desc}</div>
      </div>
      {control}
    </div>
  );
}

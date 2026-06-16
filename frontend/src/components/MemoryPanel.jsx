// Right-side drawer to manage saved memory: list facts, remove individual ones,
// or clear all. Mirrors DocumentsPanel. Click the backdrop or × to close.
export default function MemoryPanel({
  memories,
  memoryEnabled,
  onRemove,
  onClearAll,
  onClose,
}) {
  return (
    <div
      className="animate-fade-in fixed inset-0 z-40 flex justify-end bg-black/30"
      onClick={onClose}
    >
      <div
        className="animate-slide-in-right flex h-full w-80 flex-col bg-white shadow-xl dark:bg-zinc-900"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-zinc-200 px-4 py-3 dark:border-white/10">
          <h2 className="text-sm font-semibold text-zinc-800 dark:text-zinc-100">
            Memory{memories.length > 0 ? ` (${memories.length})` : ""}
            {!memoryEnabled && (
              <span className="ml-1 font-normal text-zinc-400">· off</span>
            )}
          </h2>
          <button
            onClick={onClose}
            aria-label="Close panel"
            className="grid h-7 w-7 place-items-center rounded-lg text-zinc-400 transition hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-white/10 dark:hover:text-zinc-200"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>

        <div className="flex-1 space-y-2 overflow-y-auto p-3">
          {memories.length === 0 ? (
            <p className="mt-8 text-center text-sm text-zinc-400">
              Nothing remembered yet.
            </p>
          ) : (
            memories.map((m, i) => (
              <div
                key={i}
                className="flex items-start gap-2 rounded-lg border border-zinc-200 p-2.5 dark:border-white/10"
              >
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-500" />
                <p className="min-w-0 flex-1 text-sm text-zinc-700 dark:text-zinc-200">{m}</p>
                <button
                  onClick={() => onRemove(m)}
                  aria-label="Remove fact"
                  className="shrink-0 rounded-md p-1 text-zinc-400 transition hover:bg-red-50 hover:text-red-500"
                >
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m2 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
                  </svg>
                </button>
              </div>
            ))
          )}
        </div>

        {memories.length > 0 && (
          <div className="border-t border-zinc-200 p-3 dark:border-white/10">
            <button
              onClick={onClearAll}
              className="w-full rounded-lg border border-red-200 px-3 py-2 text-sm font-medium text-red-600 transition hover:bg-red-50 dark:border-red-900 dark:text-red-400 dark:hover:bg-red-950/40"
            >
              Clear all memory
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

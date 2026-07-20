import { useState } from "react";

// Right-side drawer to manage saved memory. Two views: the fact list (quick
// per-fact remove) and the FILE itself as editable markdown — facts are its
// "- " bullets, anything else written around them is kept verbatim.
export default function MemoryPanel({
  memories,
  memoryEnabled,
  onRemove,
  onClearAll,
  onLoadMarkdown,
  onSaveMarkdown,
  onClose,
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const openEditor = async () => {
    setBusy(true);
    setError("");
    try {
      setText(await onLoadMarkdown());
      setEditing(true);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const saveEditor = async () => {
    setBusy(true);
    setError("");
    try {
      await onSaveMarkdown(text);
      setEditing(false);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

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
          <div className="flex items-center gap-1">
            <button
              onClick={editing ? () => setEditing(false) : openEditor}
              disabled={busy}
              title={editing ? "Back to the fact list" : "Edit the memory file as markdown"}
              className={`grid h-7 w-7 place-items-center rounded-lg transition hover:bg-zinc-100 dark:hover:bg-white/10 ${editing ? "text-indigo-500" : "text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200"}`}
            >
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" />
              </svg>
            </button>
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
        </div>

        {error && (
          <p className="border-b border-red-200 px-4 py-2 text-xs text-red-500 dark:border-red-900">{error}</p>
        )}

        {editing ? (
          <>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              disabled={busy}
              spellCheck={false}
              className="flex-1 resize-none bg-transparent p-3 font-mono text-[12.5px] leading-relaxed text-zinc-700 outline-none dark:text-zinc-200"
            />
            <div className="border-t border-zinc-200 p-3 dark:border-white/10">
              <p className="mb-2 text-[11px] text-zinc-400">
                Facts are the “- ” bullet lines — everything else you write here is kept as-is.
              </p>
              <button
                onClick={saveEditor}
                disabled={busy}
                className="w-full rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white transition hover:bg-indigo-700 disabled:opacity-50"
              >
                Save file
              </button>
            </div>
          </>
        ) : (
          <>
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
          </>
        )}
      </div>
    </div>
  );
}

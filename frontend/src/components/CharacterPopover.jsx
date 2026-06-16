import { useEffect, useState } from "react";

// Persona control in the header: shows the active character and opens an
// editor popover. The /character command remains an alternative input path.
const PRESETS = [
  "a concise expert who answers in short, precise sentences",
  "a friendly teacher who explains things step by step",
  "a witty pirate captain",
];

export default function CharacterPopover({ character, onChange }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(character);

  // Re-seed the draft each time the popover opens (or the persona changes
  // underneath us, e.g. via /character).
  useEffect(() => {
    if (open) setDraft(character);
  }, [open, character]);

  const save = () => {
    onChange(draft.trim());
    setOpen(false);
  };
  const clear = () => {
    onChange("");
    setOpen(false);
  };

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        title={character || "Set a persona for this chat"}
        className={`flex max-w-[260px] items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm font-medium transition ${
          character
            ? "bg-violet-50 text-violet-700 hover:bg-violet-100 dark:bg-violet-950/40 dark:text-violet-300 dark:hover:bg-violet-950/60"
            : "text-zinc-500 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-white/10"
        }`}
      >
        <MaskIcon className="h-4 w-4 shrink-0" />
        <span className="truncate">{character || "Persona"}</span>
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          <div className="animate-pop-in absolute left-0 z-40 mt-1 w-80 rounded-xl border border-zinc-200 bg-white p-3 shadow-lg dark:border-white/10 dark:bg-zinc-900">
            <div className="mb-2 flex items-center gap-2">
              <span className="grid h-7 w-7 place-items-center rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-500 text-white">
                <MaskIcon className="h-4 w-4" />
              </span>
              <div className="leading-tight">
                <div className="text-sm font-semibold text-zinc-800 dark:text-zinc-100">
                  Persona
                </div>
                <div className="text-[11px] text-zinc-400 dark:text-zinc-500">
                  This chat only — how should Noema behave?
                </div>
              </div>
            </div>

            <textarea
              rows={3}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="e.g. a sarcastic senior engineer reviewing my ideas"
              className="w-full resize-none rounded-lg border border-zinc-200 px-2.5 py-2 text-sm text-zinc-800 placeholder-zinc-400 outline-none focus:border-violet-300 dark:border-white/10 dark:bg-zinc-800 dark:text-zinc-100 dark:placeholder-zinc-500 dark:focus:border-violet-700"
            />

            <div className="mt-2 flex flex-wrap gap-1.5">
              {PRESETS.map((p) => (
                <button
                  key={p}
                  onClick={() => setDraft(p)}
                  title={p}
                  className="max-w-full truncate rounded-full bg-zinc-100 px-2.5 py-1 text-[11px] text-zinc-600 transition hover:bg-violet-100 hover:text-violet-700 dark:bg-white/5 dark:text-zinc-400 dark:hover:bg-violet-950/50 dark:hover:text-violet-300"
                >
                  {p.length > 38 ? p.slice(0, 38) + "…" : p}
                </button>
              ))}
            </div>

            <div className="mt-3 flex justify-end gap-2">
              {character && (
                <button
                  onClick={clear}
                  className="rounded-lg px-3 py-1.5 text-sm font-medium text-zinc-500 transition hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-white/10"
                >
                  Clear
                </button>
              )}
              <button
                onClick={save}
                disabled={!draft.trim() && !character}
                className="rounded-lg bg-violet-600 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Save
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// A simple theatre mask — the literal meaning of "persona", and clearly a face
// so it doesn't read as the sidebar's User icon.
function MaskIcon({ className }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 6c3-1.5 11-1.5 14 0 0 6-2 14-7 14S5 12 5 6z" />
      <circle cx="9.5" cy="10.5" r="1" fill="currentColor" stroke="none" />
      <circle cx="14.5" cy="10.5" r="1" fill="currentColor" stroke="none" />
      <path d="M9.5 14q2.5 2 5 0" />
    </svg>
  );
}

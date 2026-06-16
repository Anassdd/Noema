import { useEffect, useRef, useState } from "react";

// Shown when /forget matches several facts: pick which ones to remove.
// Keyboard: ↑↓ move the highlight, Space toggles it, Enter forgets the
// selected set, Esc cancels. Mouse: click a row to toggle. All start selected.
export default function ForgetDialog({ facts, onConfirm, onCancel }) {
  const [selected, setSelected] = useState(
    () => new Set(facts.map((_, i) => i)),
  );
  const [cursor, setCursor] = useState(0);
  const boxRef = useRef(null);

  useEffect(() => {
    boxRef.current?.focus();
  }, []);

  const toggle = (i) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });

  const allOn = selected.size === facts.length;
  const toggleAll = () =>
    setSelected(allOn ? new Set() : new Set(facts.map((_, i) => i)));

  const confirm = () => {
    const chosen = facts.filter((_, i) => selected.has(i));
    if (chosen.length) onConfirm(chosen);
  };

  const onKeyDown = (e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((c) => (c + 1) % facts.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => (c - 1 + facts.length) % facts.length);
    } else if (e.key === " ") {
      e.preventDefault();
      toggle(cursor);
    } else if (e.key === "Enter") {
      e.preventDefault();
      confirm();
    } else if (e.key === "Escape") {
      e.preventDefault();
      onCancel();
    }
  };

  return (
    <div
      className="animate-fade-in fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onCancel}
    >
      <div
        ref={boxRef}
        tabIndex={-1}
        onKeyDown={onKeyDown}
        onClick={(e) => e.stopPropagation()}
        className="animate-pop-in w-full max-w-sm rounded-2xl bg-white p-5 shadow-xl outline-none dark:bg-zinc-900"
      >
        <div className="flex items-baseline justify-between">
          <h2 className="text-base font-semibold text-zinc-800 dark:text-zinc-100">
            Forget which facts?
          </h2>
          <button
            onClick={toggleAll}
            className="text-xs font-medium text-indigo-600 transition hover:text-indigo-700 dark:text-indigo-400"
          >
            {allOn ? "Select none" : "Select all"}
          </button>
        </div>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          {facts.length} match — pick the ones to remove.
        </p>

        <ul className="mt-3 max-h-56 space-y-1 overflow-y-auto">
          {facts.map((f, i) => {
            const on = selected.has(i);
            const active = i === cursor;
            return (
              <li
                key={i}
                onMouseEnter={() => setCursor(i)}
                onClick={() => toggle(i)}
                className={`flex cursor-pointer items-start gap-2 rounded-lg px-2.5 py-2 text-sm transition ${
                  active
                    ? "bg-zinc-100 dark:bg-white/10"
                    : "hover:bg-zinc-50 dark:hover:bg-white/5"
                }`}
              >
                <span
                  className={`mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded border transition ${
                    on
                      ? "border-indigo-600 bg-indigo-600 text-white"
                      : "border-zinc-300 dark:border-zinc-600"
                  }`}
                >
                  {on && (
                    <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M20 6L9 17l-5-5" />
                    </svg>
                  )}
                </span>
                <span className="min-w-0 flex-1 text-zinc-700 dark:text-zinc-200">
                  {f}
                </span>
              </li>
            );
          })}
        </ul>

        <div className="mt-4 flex items-center justify-end gap-2">
          <button
            onClick={onCancel}
            className="rounded-lg px-3 py-2 text-sm font-medium text-zinc-600 transition hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-white/10"
          >
            Cancel
          </button>
          <button
            onClick={confirm}
            disabled={selected.size === 0}
            className="rounded-lg bg-red-600 px-3 py-2 text-sm font-medium text-white transition hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Forget {selected.size || ""}
          </button>
        </div>
        <p className="mt-2 text-center text-[10px] text-zinc-400 dark:text-zinc-500">
          ↑↓ move · Space toggle · Enter forget · Esc cancel
        </p>
      </div>
    </div>
  );
}

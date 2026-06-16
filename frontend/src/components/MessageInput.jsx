import { useRef, useState } from "react";

import { estimateTokens } from "../lib/tokens.js";
import { findCommand, matchCommands } from "../lib/commands.js";

// Pill-shaped composer with an auto-growing textarea and a circular send/stop
// button. Enter sends, Shift+Enter inserts a newline. A recognized command is
// colored in place via a backdrop overlay behind a transparent-text textarea.
export default function MessageInput({
  onSend,
  onStop,
  isStreaming,
  showTokenEstimate,
  onAttach,
  isUploading,
}) {
  const [text, setText] = useState("");
  const [selIdx, setSelIdx] = useState(0);
  const [menuDismissed, setMenuDismissed] = useState(false);
  const taRef = useRef(null);
  const fileRef = useRef(null);
  const overlayRef = useRef(null);
  // Only tokenize when the estimate is actually shown.
  const estTokens = showTokenEstimate ? estimateTokens(text) : 0;
  const command = findCommand(text.trim());
  const suggestions = menuDismissed ? [] : matchCommands(text.trim());
  // Keep the highlight inside the (possibly shrinking) suggestion list.
  const highlighted = Math.min(selIdx, Math.max(0, suggestions.length - 1));

  const completeCommand = (cmd) => {
    setText(cmd + " ");
    setSelIdx(0);
    taRef.current?.focus();
  };

  const onFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) onAttach?.(file);
    e.target.value = ""; // allow re-selecting the same file
  };

  const resize = () => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  };

  // Keep the color overlay aligned when the textarea scrolls internally.
  const syncScroll = () => {
    if (overlayRef.current && taRef.current) {
      overlayRef.current.scrollTop = taRef.current.scrollTop;
    }
  };

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed || isStreaming) return;
    onSend(trimmed);
    setText("");
    requestAnimationFrame(resize);
  };

  const onKeyDown = (e) => {
    // While the command menu is open: ↑↓ choose, Enter/Tab complete, Esc hides.
    if (suggestions.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelIdx((highlighted + 1) % suggestions.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelIdx((highlighted - 1 + suggestions.length) % suggestions.length);
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        completeCommand(suggestions[highlighted].cmd);
        return;
      }
      if (e.key === "Escape") {
        setMenuDismissed(true);
        return;
      }
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const canSend = text.trim().length > 0;

  return (
    <div className="relative">
      {suggestions.length > 0 && (
        <div className="animate-pop-in absolute bottom-full left-0 z-30 mb-2 w-80 rounded-xl border border-zinc-200 bg-white p-1.5 shadow-lg dark:border-white/10 dark:bg-zinc-900">
          {suggestions.map((s, i) => (
            <button
              key={s.cmd}
              onClick={() => completeCommand(s.cmd)}
              onMouseEnter={() => setSelIdx(i)}
              className={`flex w-full items-baseline gap-2 rounded-lg px-3 py-2 text-left transition ${
                i === highlighted
                  ? "bg-zinc-100 dark:bg-white/10"
                  : "hover:bg-zinc-50 dark:hover:bg-white/5"
              }`}
            >
              <span className={`font-mono text-sm font-semibold ${s.text}`}>
                {s.cmd}
              </span>
              <span className="text-xs text-zinc-500 dark:text-zinc-400">
                {s.desc}
              </span>
            </button>
          ))}
          <p className="px-3 pb-1 pt-1.5 text-[10px] text-zinc-400 dark:text-zinc-500">
            ↑↓ choose · Enter or Tab to complete · Esc to hide
          </p>
        </div>
      )}
      {command && (
        <div
          className={`mb-2 inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs ring-1 ${command.chip}`}
        >
          <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M13 2L3 14h7l-1 8 10-12h-7l1-8z" />
          </svg>
          <span className="font-medium">{command.label} command</span>
          <span className="opacity-70">· {command.desc.toLowerCase()}</span>
        </div>
      )}
      <div
        className={`flex items-end gap-2 rounded-3xl border bg-white p-2 pl-2 shadow-sm transition focus-within:shadow-md dark:bg-zinc-900 ${
          command
            ? "border-zinc-300 dark:border-white/25"
            : "border-zinc-200 focus-within:border-zinc-300 dark:border-white/15 dark:focus-within:border-white/25"
        }`}
      >
        <input
          ref={fileRef}
          type="file"
          accept="application/pdf,.pdf"
          className="hidden"
          onChange={onFileChange}
        />
        <button
          onClick={() => fileRef.current?.click()}
          disabled={isUploading}
          aria-label="Attach PDF"
          title="Attach a PDF"
          className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-700 disabled:cursor-not-allowed disabled:opacity-50 dark:text-zinc-400 dark:hover:bg-white/10 dark:hover:text-zinc-200"
        >
          {isUploading ? (
            <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 12a9 9 0 1 1-6.219-8.56" strokeLinecap="round" />
            </svg>
          ) : (
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
            </svg>
          )}
        </button>

        {/* Backdrop overlay colors the command word; the textarea above it
            keeps the caret + editing, with transparent text while active. */}
        <div className="relative min-w-0 flex-1">
          {command && (
            <div
              ref={overlayRef}
              aria-hidden
              className="pointer-events-none absolute inset-0 overflow-hidden whitespace-pre-wrap break-words py-2 text-sm"
            >
              <span className={`font-semibold ${command.text}`}>
                {command.word}
              </span>
              <span className="text-zinc-800 dark:text-zinc-100">
                {command.rest}
              </span>
            </div>
          )}
          <textarea
            ref={taRef}
            rows={1}
            className={`max-h-52 w-full resize-none bg-transparent py-2 text-sm placeholder-zinc-400 outline-none dark:placeholder-zinc-500 ${
              command
                ? "text-transparent caret-zinc-800 dark:caret-zinc-100"
                : "text-zinc-800 dark:text-zinc-100"
            }`}
            placeholder="Message Noema…"
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setMenuDismissed(false); // typing re-opens a dismissed menu
              resize();
            }}
            onKeyDown={onKeyDown}
            onScroll={syncScroll}
          />
        </div>

        {isStreaming ? (
          <button
            onClick={onStop}
            aria-label="Stop generating"
            className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-zinc-800 text-white transition hover:bg-zinc-700 dark:bg-zinc-200 dark:text-zinc-900 dark:hover:bg-white"
          >
            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="currentColor">
              <rect x="6" y="6" width="12" height="12" rx="2" />
            </svg>
          </button>
        ) : (
          <button
            onClick={submit}
            disabled={!canSend}
            aria-label="Send message"
            className={`grid h-9 w-9 shrink-0 place-items-center rounded-full transition ${
              canSend
                ? "bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow-sm hover:from-indigo-600 hover:to-violet-700"
                : "cursor-not-allowed bg-zinc-200 text-zinc-400 dark:bg-zinc-800 dark:text-zinc-600"
            }`}
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 19V5M5 12l7-7 7 7" />
            </svg>
          </button>
        )}
      </div>
      {showTokenEstimate && (
        <div className="h-4 px-3 pt-1 text-right text-[11px] text-zinc-400 dark:text-zinc-500">
          {estTokens > 0 && (
            <span title="Exact token count of your message (tiktoken o200k_base, used by gpt-4o/4o-mini). Excludes history and per-message overhead.">
              {estTokens.toLocaleString()} input tokens
            </span>
          )}
        </div>
      )}
    </div>
  );
}

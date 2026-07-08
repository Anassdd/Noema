import { useRef, useState } from "react";

import { estimateTokens } from "../lib/tokens.js";
import { findCommand, matchCommands } from "../lib/commands.js";
import { listSaves } from "../api/graphmem.js";
import { PlusIcon, SendIcon, StopIcon, SparkIcon, Icon, ChevronDownIcon, CheckIcon } from "./icons.jsx";

// Rounded composer (mockup style): auto-growing textarea, a circular attach
// button and a circular send/stop button, with a token + model footer. A
// recognized command is colored in place via a backdrop overlay behind a
// transparent-text textarea.
export default function MessageInput({
  onSend,
  onStop,
  isStreaming,
  showTokenEstimate,
  onAttach,
  isUploading,
  model,
  sessionTokens,
  memory,
  onSelectMemory,
  retrieval,
  onSelectRetrieval,
  expertEnabled,
}) {
  const [text, setText] = useState("");
  const [selIdx, setSelIdx] = useState(0);
  const [menuDismissed, setMenuDismissed] = useState(false);
  const taRef = useRef(null);
  const fileRef = useRef(null);
  const overlayRef = useRef(null);

  const estTokens = showTokenEstimate ? estimateTokens(text) : 0;
  const command = findCommand(text.trim());
  const suggestions = menuDismissed ? [] : matchCommands(text.trim());
  const highlighted = Math.min(selIdx, Math.max(0, suggestions.length - 1));

  const completeCommand = (cmd) => {
    setText(cmd + " ");
    setSelIdx(0);
    taRef.current?.focus();
  };

  const onFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) onAttach?.(file);
    e.target.value = "";
  };

  const resize = () => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  };

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
    <div className="relative mx-auto w-full max-w-[720px]">
      {suggestions.length > 0 && (
        <div
          className="animate-pop-in absolute bottom-full left-0 z-30 mb-2 w-80 rounded-xl border p-1.5"
          style={{
            background: "var(--sidebar-bg)",
            borderColor: "var(--border)",
            boxShadow: "var(--win-shadow)",
          }}
        >
          {suggestions.map((s, i) => (
            <button
              key={s.cmd}
              onClick={() => completeCommand(s.cmd)}
              onMouseEnter={() => setSelIdx(i)}
              className="flex w-full items-baseline gap-2 rounded-lg px-3 py-2 text-left transition"
              style={{ background: i === highlighted ? "var(--row-hover)" : "transparent" }}
            >
              <span className={`font-mono text-sm font-semibold ${s.text}`}>{s.cmd}</span>
              <span className="text-xs" style={{ color: "var(--text-soft)" }}>
                {s.desc}
              </span>
            </button>
          ))}
          <p className="px-3 pb-1 pt-1.5 text-[10px]" style={{ color: "var(--text-faint)" }}>
            ↑↓ choose · Enter or Tab to complete · Esc to hide
          </p>
        </div>
      )}

      {command && (
        <div
          className="mb-2 inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs"
          style={{
            color: "var(--accent)",
            background: "var(--accent-soft)",
            border: "1px solid var(--accent-border)",
          }}
        >
          <SparkIcon size={13} />
          <span className="font-medium">{command.label} command</span>
          <span style={{ opacity: 0.7 }}>· {command.desc.toLowerCase()}</span>
        </div>
      )}

      <div
        className="flex flex-col gap-3 rounded-[20px] border p-3.5"
        style={{
          background: "var(--user-bubble)",
          borderColor: "var(--border)",
          boxShadow: "0 1px 2px rgba(0,0,0,.05), 0 12px 30px rgba(20,28,80,.08)",
        }}
      >
        <div className="relative min-w-0 flex-1">
          {command && (
            <div
              ref={overlayRef}
              aria-hidden
              className="pointer-events-none absolute inset-0 overflow-hidden whitespace-pre-wrap break-words text-[15px] leading-relaxed"
            >
              <span className={`font-semibold ${command.text}`}>{command.word}</span>
              <span style={{ color: "var(--text)" }}>{command.rest}</span>
            </div>
          )}
          <textarea
            ref={taRef}
            rows={1}
            className="max-h-52 w-full resize-none bg-transparent text-[15px] leading-relaxed outline-none"
            style={{ color: command ? "transparent" : "var(--text)", caretColor: "var(--text)" }}
            placeholder="Ask Noema anything…"
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setMenuDismissed(false);
              resize();
            }}
            onKeyDown={onKeyDown}
            onScroll={syncScroll}
          />
        </div>

        <div className="flex items-center gap-2.5">
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
            className="grid h-8 w-8 shrink-0 place-items-center rounded-full disabled:opacity-50"
            style={{ background: "var(--plus-bg)", color: "var(--plus-fg)" }}
          >
            {isUploading ? (
              <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 12a9 9 0 1 1-6.219-8.56" strokeLinecap="round" />
              </svg>
            ) : (
              <PlusIcon size={16} sw={1.9} />
            )}
          </button>

          {expertEnabled && <MemorySelector value={memory} onChange={onSelectMemory} />}
          {expertEnabled && <RetrievalSelector value={retrieval} onChange={onSelectRetrieval} />}

          <div className="ml-auto" />

          {isStreaming ? (
            <button
              onClick={onStop}
              aria-label="Stop generating"
              className="grid h-9 w-9 shrink-0 place-items-center rounded-full"
              style={{ background: "var(--send-bg)", color: "var(--send-fg)" }}
            >
              <StopIcon size={14} />
            </button>
          ) : (
            <button
              onClick={submit}
              disabled={!canSend}
              aria-label="Send message"
              className="grid h-9 w-9 shrink-0 place-items-center rounded-full transition disabled:opacity-40"
              style={{ background: "var(--send-bg)", color: "var(--send-fg)" }}
            >
              <SendIcon size={16} sw={2.2} />
            </button>
          )}
        </div>
      </div>

      <div
        className="mt-2.5 flex items-center px-1 font-mono text-[11px]"
        style={{ color: "var(--text-faint)" }}
      >
        <span>{memory ? `Answering from “${memory}”.` : "Answers may be inaccurate."}</span>
        <span className="ml-auto flex items-center gap-3.5">
          {showTokenEstimate && estTokens > 0 && (
            <span title="Exact token count of your message (tiktoken o200k_base).">
              {estTokens.toLocaleString()} input tok
            </span>
          )}
          {sessionTokens > 0 && <span>Σ {sessionTokens.toLocaleString()} tok</span>}
          {model && <span style={{ color: "var(--accent)" }}>{model}</span>}
        </span>
      </div>
    </div>
  );
}

// Pick which memory the expert grounds answers in: the live working memory, or one of the
// saved snapshots (each captures the graph + RAG together). Saves are made on the graph page.
function MemorySelector({ value, onChange }) {
  const [open, setOpen] = useState(false);
  const [saves, setSaves] = useState([]);
  const toggle = () => {
    if (!open) listSaves().then((r) => setSaves(r.saves || [])).catch(() => {});
    setOpen((o) => !o);
  };
  const active = !!value;
  return (
    <div className="relative">
      <button
        onClick={toggle}
        title="Which memory the expert answers from"
        className="flex items-center gap-1.5 rounded-full border px-2.5 py-1.5 text-xs transition"
        style={{
          borderColor: active ? "var(--accent-border)" : "var(--border)",
          color: active ? "var(--accent)" : "var(--text-soft)",
          background: active ? "var(--accent-soft)" : "transparent",
        }}
      >
        <Icon size={12} sw={1.8}>
          <ellipse cx="12" cy="5" rx="8" ry="3" />
          <path d="M4 5v6c0 1.66 3.58 3 8 3s8-1.34 8-3V5" />
          <path d="M4 11v6c0 1.66 3.58 3 8 3s8-1.34 8-3v-6" />
        </Icon>
        <span className="max-w-[130px] truncate">{value || "Live memory"}</span>
        <ChevronDownIcon size={12} sw={2} />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-20" onClick={() => setOpen(false)} />
          <div
            className="animate-pop-in absolute bottom-full left-0 z-30 mb-2 max-h-72 w-60 overflow-y-auto rounded-xl border p-1.5"
            style={{ background: "var(--sidebar-bg)", borderColor: "var(--border)", boxShadow: "var(--win-shadow)" }}
          >
            <MemoryItem active={!value} onClick={() => { onChange(null); setOpen(false); }}
              label="Live memory" hint="the current working memory" />
            {saves.map((s) => (
              <MemoryItem key={s} active={value === s} onClick={() => { onChange(s); setOpen(false); }}
                label={s} hint="saved snapshot" />
            ))}
            {saves.length === 0 && (
              <p className="px-3 py-2 text-[11px]" style={{ color: "var(--text-faint)" }}>
                No saved memories yet — save one on the graph page.
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}

// Which store answers: both fused (the product default), the contextual vector base
// alone, or the knowledge graph alone — so the methods can be compared live in chat.
const RETRIEVAL_MODES = [
  { id: "hybrid", label: "Hybrid", hint: "vector base + graph, fused (default)" },
  { id: "rag", label: "Vector only", hint: "contextual RAG alone — graph off" },
  { id: "graph", label: "Graph only", hint: "knowledge graph alone — RAG off" },
];

function RetrievalSelector({ value, onChange }) {
  const [open, setOpen] = useState(false);
  const mode = RETRIEVAL_MODES.find((m) => m.id === value) || RETRIEVAL_MODES[0];
  const active = mode.id !== "hybrid";
  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        title="Which store the expert retrieves from"
        className="flex items-center gap-1.5 rounded-full border px-2.5 py-1.5 text-xs transition"
        style={{
          borderColor: active ? "var(--accent-border)" : "var(--border)",
          color: active ? "var(--accent)" : "var(--text-soft)",
          background: active ? "var(--accent-soft)" : "transparent",
        }}
      >
        <Icon size={12} sw={1.8}>
          <circle cx="6" cy="6" r="2.5" />
          <circle cx="18" cy="6" r="2.5" />
          <circle cx="12" cy="18" r="2.5" />
          <path d="M7.8 7.8l3 7.4M16.2 7.8l-3 7.4" />
        </Icon>
        <span className="max-w-[110px] truncate">{mode.label}</span>
        <ChevronDownIcon size={12} sw={2} />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-20" onClick={() => setOpen(false)} />
          <div
            className="animate-pop-in absolute bottom-full left-0 z-30 mb-2 w-64 rounded-xl border p-1.5"
            style={{ background: "var(--sidebar-bg)", borderColor: "var(--border)", boxShadow: "var(--win-shadow)" }}
          >
            {RETRIEVAL_MODES.map((m) => (
              <MemoryItem key={m.id} active={mode.id === m.id}
                onClick={() => { onChange(m.id); setOpen(false); }}
                label={m.label} hint={m.hint} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function MemoryItem({ active, onClick, label, hint }) {
  return (
    <button
      onClick={onClick}
      className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left transition hover:bg-[var(--row-hover)]"
    >
      <span className="grid h-4 w-4 shrink-0 place-items-center" style={{ color: "var(--accent)" }}>
        {active ? <CheckIcon size={13} sw={2.6} /> : null}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13px]" style={{ color: "var(--text)" }}>{label}</span>
        <span className="block text-[10px]" style={{ color: "var(--text-faint)" }}>{hint}</span>
      </span>
    </button>
  );
}

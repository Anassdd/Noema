import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";

import { COMMANDS } from "../lib/commands.js";
import { CheckIcon, Icon } from "./icons.jsx";

// Markdown (parser + highlighter) is heavy — lazy-load it into its own chunk.
const Markdown = lazy(() => import("./Markdown.jsx"));

// Renders the conversation: user turns as a right-aligned bubble, assistant
// turns as a serif "N" avatar + mono label above the answer. Auto-scrolls only
// while the user is already near the bottom.
export default function MessageList({ messages, isStreaming, containerRef }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    const el = containerRef?.current;
    if (el) {
      const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
      if (!nearBottom) return;
    }
    // Instant while streaming: a per-token smooth scroll lags behind the
    // growing answer and shows the empty area scrolling by. Smooth otherwise.
    bottomRef.current?.scrollIntoView({ behavior: isStreaming ? "auto" : "smooth" });
  }, [messages, isStreaming, containerRef]);

  // Split each answer's prompt tokens into context (carried over) vs. prompt
  // (the new user message). Stays additive: context + prompt + response.
  let prevContext = 0;
  const rows = messages.map((m) => {
    let breakdown = null;
    if (m.role === "assistant" && m.usage) {
      const history = Math.min(prevContext, m.usage.prompt_tokens);
      const input = m.usage.prompt_tokens - history;
      breakdown = {
        history,
        input,
        output: m.usage.completion_tokens,
        total: m.usage.total_tokens,
      };
      prevContext = m.usage.prompt_tokens + m.usage.completion_tokens;
    }
    return { m, breakdown };
  });

  const followReveal = () => {
    const el = containerRef?.current;
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight > 160) return;
    bottomRef.current?.scrollIntoView();
  };

  return (
    <div className="mx-auto flex max-w-[720px] flex-col gap-7 px-7 py-8">
      {rows.map(({ m, breakdown }, i) => (
        <Row
          key={i}
          message={m}
          breakdown={breakdown}
          showCursor={isStreaming && i === messages.length - 1 && m.role === "assistant"}
          isLast={i === messages.length - 1 && m.role === "assistant"}
          onProgress={followReveal}
        />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}

function Row({ message, breakdown, showCursor, isLast, onProgress }) {
  const isUser = message.role === "user";
  const [revealDone, setRevealDone] = useState(false);

  if (message.role === "help") {
    return (
      <div className="animate-message-in flex justify-center">
        <div
          className="w-full max-w-md rounded-2xl border p-4"
          style={{ background: "var(--user-bubble)", borderColor: "var(--border)" }}
        >
          <div className="mb-3 text-sm font-semibold" style={{ color: "var(--text)" }}>
            Commands
          </div>
          <div className="space-y-3">
            {COMMANDS.map((c) => (
              <div key={c.cmd} className="text-sm">
                <div className="flex items-baseline gap-2">
                  <span className={`font-mono font-semibold ${c.text}`}>{c.cmd}</span>
                  <span style={{ color: "var(--text-soft)" }}>{c.desc}</span>
                </div>
                <div className="mt-0.5 text-xs" style={{ color: "var(--text-faint)" }}>
                  {c.hint}{" "}
                  <span className="font-mono text-[11px]">e.g. {c.usage}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (message.role === "note") {
    return (
      <div className="animate-message-in flex justify-center">
        <div
          className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 font-mono text-[11px]"
          style={{ background: "var(--accent-soft)", color: "var(--accent)", border: "1px solid var(--accent-border)" }}
        >
          <CheckIcon size={12} sw={2.2} />
          {message.content}
        </div>
      </div>
    );
  }

  if (isUser) {
    return (
      <div className="animate-message-in flex justify-end">
        <div
          className="max-w-[82%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-[15px] leading-relaxed"
          style={{ background: "var(--user-bubble)", border: "1px solid var(--user-bubble-border)", color: "var(--text)" }}
        >
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="animate-message-in">
      <div className="mb-2.5 flex items-center gap-2">
        <span
          className={`font-serif grid h-5 w-5 place-items-center rounded-full text-[12px] ${showCursor ? "avatar-streaming" : ""}`}
          style={{ background: "var(--accent-soft)", color: "var(--accent)" }}
        >
          N
        </span>
        <span
          className="font-mono text-[10px] uppercase"
          style={{ letterSpacing: ".08em", color: "var(--text-faint)" }}
        >
          Noema
        </span>
      </div>
      {message.content ? (
        isLast ? (
          <PacedAnswer
            text={message.content}
            streaming={showCursor}
            onProgress={onProgress}
            onDone={() => setRevealDone(true)}
          />
        ) : (
          <MarkdownBlock content={message.content} />
        )
      ) : showCursor ? (
        <TypingDots />
      ) : null}
      {!showCursor && (!isLast || revealDone) && message.content && (
        <div className="mt-2 flex items-center gap-2 font-mono text-[11px]" style={{ color: "var(--text-faint)" }}>
          <CopyButton text={message.content} />
          {breakdown && (
            <span>
              <span title="Tokens carried over from earlier turns">
                context {breakdown.history.toLocaleString()}
              </span>
              {" + "}
              <span title="Tokens added by your new message this turn">
                prompt {breakdown.input.toLocaleString()}
              </span>
              {" + "}
              <span title="Tokens the model generated">
                response {breakdown.output.toLocaleString()}
              </span>
              {" = "}
              <span style={{ color: "var(--text-soft)" }}>
                {breakdown.total.toLocaleString()} tokens
              </span>
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function MarkdownBlock({ content }) {
  return (
    <div className="md text-[15.5px]" style={{ lineHeight: 1.8, color: "var(--assistant-text)" }}>
      <Suspense fallback={<div className="whitespace-pre-wrap">{content}</div>}>
        <Markdown>{content}</Markdown>
      </Suspense>
    </div>
  );
}

// ---- Paced word reveal ------------------------------------------------------
const FADE_STEP = 45;
const FADE_LEAD = 120;

function buildSegments(text) {
  const segs = [];
  const lines = text.split("\n");
  lines.forEach((line, li) => {
    const parts = line.split(/(\s+)/).filter(Boolean);
    for (let i = 0; i < parts.length; i++) {
      if (/^\s+$/.test(parts[i])) continue;
      const next = parts[i + 1];
      const trailing = next && /^\s+$/.test(next) ? " " : "";
      segs.push({ type: "word", text: parts[i] + trailing });
    }
    if (li < lines.length - 1) segs.push({ type: "break" });
  });
  return segs;
}

function PacedAnswer({ text, streaming, onProgress, onDone }) {
  const segs = useMemo(() => buildSegments(text), [text]);
  const total = useMemo(() => segs.filter((s) => s.type === "word").length, [segs]);
  const [paced] = useState(streaming);
  const [shown, setShown] = useState(streaming ? 0 : Number.MAX_SAFE_INTEGER);
  const caughtUp = shown >= total && !streaming;

  useEffect(() => {
    if (!paced || shown >= total) return;
    const backlog = total - shown;
    const burst = backlog > 50 ? 3 : backlog > 20 ? 2 : 1;
    const timer = setTimeout(
      () => {
        setShown((s) => Math.min(s + burst, total));
        onProgress?.();
      },
      shown === 0 ? FADE_LEAD : FADE_STEP,
    );
    return () => clearTimeout(timer);
  }, [paced, shown, total, onProgress]);

  useEffect(() => {
    if (caughtUp) onDone?.();
  }, [caughtUp, onDone]);

  if (!paced || caughtUp) return <MarkdownBlock content={text} />;

  let w = -1;
  return (
    <div className="whitespace-pre-wrap text-[15.5px]" style={{ lineHeight: 1.8, color: "var(--assistant-text)" }}>
      {segs.map((s, i) => {
        if (s.type === "break") return <br key={i} />;
        w += 1;
        return (
          <span key={i} className={"wf-w" + (w < shown ? " in" : "")}>
            {s.text}
          </span>
        );
      })}
    </div>
  );
}

function TypingDots() {
  return (
    <div className="flex h-6 items-center gap-1">
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          className="typing-dot h-1.5 w-1.5 rounded-full"
          style={{ background: "var(--text-faint)", animationDelay: `${delay}ms` }}
        />
      ))}
    </div>
  );
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };
  return (
    <button
      onClick={copy}
      aria-label="Copy message"
      title={copied ? "Copied" : "Copy"}
      className="grid h-6 w-6 place-items-center rounded-md transition hover:bg-[var(--row-hover)]"
      style={{ color: "var(--text-faint)" }}
    >
      {copied ? (
        <CheckIcon size={14} sw={2.5} />
      ) : (
        <Icon size={14}>
          <rect x="9" y="9" width="13" height="13" rx="2" />
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
        </Icon>
      )}
    </button>
  );
}

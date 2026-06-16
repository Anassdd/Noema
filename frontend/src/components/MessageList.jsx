import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";

import { COMMANDS } from "../lib/commands.js";

// Markdown (parser + highlighter) is heavy — lazy-load it into its own chunk.
// Until it arrives, answers render as plain text via the Suspense fallback.
const Markdown = lazy(() => import("./Markdown.jsx"));

// Renders the conversation, ChatGPT style: user turns as a right-aligned
// bubble, assistant turns as avatar + markdown. Auto-scrolls only while the
// user is already near the bottom (so reading back isn't hijacked).
export default function MessageList({ messages, isStreaming, containerRef }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    const el = containerRef?.current;
    if (el) {
      const nearBottom =
        el.scrollHeight - el.scrollTop - el.clientHeight < 120;
      if (!nearBottom) return;
    }
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, containerRef]);

  // Split each answer's prompt tokens into context (everything carried over
  // from prior turns) vs. prompt (what the new user message added). The API
  // only reports the combined prompt_tokens, so we derive context from the
  // previous turn's total. Stays exactly additive: context + prompt + response.
  let prevContext = 0; // prompt + completion of the last answered turn
  const rows = messages.map((m) => {
    let breakdown = null;
    if (m.role === "assistant" && m.usage) {
      // Cap context at the actual prompt size: when the prompt shrinks between
      // turns (PDF detached, history trimmed), the previous turn's total is no
      // longer a valid baseline and would break the addition.
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

  // Follow the paced reveal too (its ticks don't change `messages`).
  const followReveal = () => {
    const el = containerRef?.current;
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight > 160) return;
    bottomRef.current?.scrollIntoView();
  };

  return (
    <div className="mx-auto max-w-3xl px-4 py-6">
      {rows.map(({ m, breakdown }, i) => (
        <Row
          key={i}
          message={m}
          breakdown={breakdown}
          showCursor={
            isStreaming && i === messages.length - 1 && m.role === "assistant"
          }
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
  // The paced reveal lags behind the stream; hold the copy/token meta line
  // back until the last word has actually landed.
  const [revealDone, setRevealDone] = useState(false);

  // The /help command guide — a local card, never sent to the model.
  if (message.role === "help") {
    return (
      <div className="animate-message-in mb-6 flex justify-center">
        <div className="w-full max-w-md rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-zinc-900">
          <div className="mb-3 text-sm font-semibold text-zinc-800 dark:text-zinc-100">
            Commands
          </div>
          <div className="space-y-3">
            {COMMANDS.map((c) => (
              <div key={c.cmd} className="text-sm">
                <div className="flex items-baseline gap-2">
                  <span className={`font-mono font-semibold ${c.text}`}>
                    {c.cmd}
                  </span>
                  <span className="text-zinc-600 dark:text-zinc-300">
                    {c.desc}
                  </span>
                </div>
                <div className="mt-0.5 text-xs text-zinc-400 dark:text-zinc-500">
                  {c.hint}{" "}
                  <span className="font-mono text-[11px] text-zinc-400 dark:text-zinc-500">
                    e.g. {c.usage}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // Local system note, e.g. a /remember confirmation. Never sent to the model.
  if (message.role === "note") {
    return (
      <div className="animate-message-in mb-6 flex justify-center">
        <div className="inline-flex items-center gap-1.5 rounded-full bg-indigo-50 px-3 py-1 text-xs text-indigo-700 ring-1 ring-indigo-200 dark:bg-indigo-950/40 dark:text-indigo-300 dark:ring-indigo-900">
          <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20 6L9 17l-5-5" />
          </svg>
          {message.content}
        </div>
      </div>
    );
  }

  if (isUser) {
    return (
      <div className="animate-message-in mb-6 flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-3xl rounded-br-md bg-zinc-100 px-4 py-2.5 text-sm text-zinc-800 dark:bg-white/10 dark:text-zinc-100">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="animate-message-in mb-6 flex gap-3">
      <BotAvatar streaming={showCursor} />
      <div className="min-w-0 flex-1 pt-0.5">
        {message.content ? (
          isLast ? (
            // Newest answer: words reveal on a timer (visible fade) and
            // markdown takes over once the reveal catches up.
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
          <div className="mt-2 flex items-center gap-2 text-[11px] text-zinc-400 dark:text-zinc-500">
            <CopyButton text={message.content} />
            {breakdown && (
              <span>
                <span title="Tokens carried over from earlier turns (system + prior messages)">
                  context {breakdown.history.toLocaleString()}
                </span>
                {" + "}
                <span title="Tokens added by your new message this turn">
                  prompt {breakdown.input.toLocaleString()}
                </span>
                {" + "}
                <span title="Tokens the model generated (the answer)">
                  response {breakdown.output.toLocaleString()}
                </span>
                {" = "}
                <span className="text-zinc-500 dark:text-zinc-400">
                  {breakdown.total.toLocaleString()} tokens
                </span>
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function MarkdownBlock({ content }) {
  return (
    <div className="text-sm leading-relaxed text-zinc-800 dark:text-zinc-200">
      <Suspense fallback={<div className="whitespace-pre-wrap">{content}</div>}>
        <Markdown>{content}</Markdown>
      </Suspense>
    </div>
  );
}

// ---- Paced word reveal ------------------------------------------------------
// Streaming deltas arrive in bursts far faster than the eye can follow, so the
// fade is invisible if words show on arrival. Instead, arriving text fills a
// buffer and words are *revealed* on a fixed timer — the cadence reads like
// generation. When the backlog grows, several words land per tick so the
// reveal never trails the model by more than a few seconds.
const FADE_STEP = 45; // ms between reveal ticks
const FADE_LEAD = 120; // small lead-in before the first word

// -> array of { type:'word', text } | { type:'break' }. Each word keeps its
// trailing space inside the span (white-space:pre), so spacing stays even and
// words never fracture. Newlines become <br>.
function buildSegments(text) {
  const segs = [];
  const lines = text.split("\n");
  lines.forEach((line, li) => {
    const parts = line.split(/(\s+)/).filter(Boolean);
    for (let i = 0; i < parts.length; i++) {
      if (/^\s+$/.test(parts[i])) continue; // leading/duplicate whitespace
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
  const total = useMemo(
    () => segs.filter((s) => s.type === "word").length,
    [segs],
  );
  // Pace only when mounted mid-stream. A finished answer (e.g. switching back
  // to this conversation) renders instantly as markdown.
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
    <div className="whitespace-pre-wrap text-sm leading-relaxed text-zinc-800 dark:text-zinc-200">
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

// Three dots pulsing in sequence while waiting for the first token.
function TypingDots() {
  return (
    <div className="flex h-6 items-center gap-1">
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          className="typing-dot h-1.5 w-1.5 rounded-full bg-zinc-400 dark:bg-zinc-500"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </div>
  );
}

// Copies the message text to the clipboard, flashing a check for ~1.5s.
function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable (e.g. non-HTTPS) — silently ignore */
    }
  };

  return (
    <button
      onClick={copy}
      aria-label="Copy message"
      title={copied ? "Copied" : "Copy"}
      className="grid h-6 w-6 place-items-center rounded-md text-zinc-400 transition hover:bg-zinc-100 hover:text-zinc-600 dark:text-zinc-500 dark:hover:bg-white/10 dark:hover:text-zinc-300"
    >
      {copied ? (
        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M20 6L9 17l-5-5" />
        </svg>
      ) : (
        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="9" y="9" width="13" height="13" rx="2" />
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
        </svg>
      )}
    </button>
  );
}

function BotAvatar({ streaming }) {
  return (
    <div
      className={`grid h-8 w-8 shrink-0 place-items-center rounded-full bg-zinc-900 text-xs font-bold tracking-tight text-white dark:bg-white dark:text-zinc-900 ${
        streaming ? "avatar-streaming" : ""
      }`}
    >
      N
    </div>
  );
}

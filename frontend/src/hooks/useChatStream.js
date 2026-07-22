import { useCallback, useRef, useState } from "react";

import { NO_MEMORY, streamChat } from "../api/chat.js";
import { buildSystemMessage } from "../lib/systemPrompt.js";
import {
  looksMemorable,
  looksPastReferential,
  replyLooksMemorable,
} from "../lib/memoryFilter.js";

// Runs one chat turn: builds the request (system prompt + real turns), streams
// the answer into the in-flight assistant message, then fires the
// fire-and-forget extras — auto-title on the first exchange, and the LLM memory
// judge when warranted. Owns the streaming/error/abort state.
export function useChatStream({
  messages,
  setMessages,
  character,
  memoryContext,
  memoryReady,
  documents,
  memoryEnabled,
  prefilterEnabled,
  expertEnabled,
  memory = null,
  retrieval = null,
  domain = "default",
  model,
  onUsage,
  onAutoTitle,
  onJudgeMemory,
  onMemoryNote,
}) {
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState(null);
  const abortRef = useRef(null);
  // Frozen at the conversation's first message (Hermes' snapshot pattern): the
  // memory block sits in the CACHED prompt prefix, so mutating it mid-chat
  // would re-bill the whole prefix every turn. Costs nothing in freshness —
  // anything learned mid-conversation is already in the transcript; the file
  // only needs to be current for the NEXT chat.
  const frozenMemory = useRef(null);

  const sendMessage = useCallback(
    async (text) => {
      const userMsg = { role: "user", content: text };
      const isFirstExchange = messages.length === 0;
      const shown = [...messages, userMsg]; // displayed transcript (may have notes)

      setMessages([...shown, { role: "assistant", content: "" }]);
      setError(null);
      setIsStreaming(true);

      // What the model sees: real turns only (notes/help stripped), with the
      // persona + documents + long-term memory pinned in front. When memory is
      // off, the memory block is withheld from the prompt. The freeze waits
      // for the memory fetch — a fast first message must not lock in an empty
      // block just because the load hadn't resolved yet.
      if (frozenMemory.current === null && memoryReady) {
        frozenMemory.current = memoryContext ?? "";
      }
      const liveMemory =
        frozenMemory.current !== null ? frozenMemory.current : (memoryContext ?? "");
      const sys = buildSystemMessage(
        character,
        memoryEnabled ? liveMemory || null : null,
        documents,
      );
      const turns = shown.filter(
        (m) => m.role === "user" || m.role === "assistant",
      );
      const history = sys ? [sys, ...turns] : turns;


      const controller = new AbortController();
      abortRef.current = controller;

      // Accumulate the reply locally too, to hand the full exchange to the
      // memory judge once streaming finishes.
      let answer = "";
      const appendToAssistant = (chunk) => {
        answer += chunk;
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          next[next.length - 1] = { ...last, content: last.content + chunk };
          return next;
        });
      };

      const attachUsage = (usage) => {
        onUsage?.(usage); // feed the session-wide token meter
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          next[next.length - 1] = { ...last, usage };
          return next;
        });
      };

      const patchLast = (patch) =>
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          next[next.length - 1] = { ...last, ...patch(last) };
          return next;
        });
      const appendTrace = (step) => patchLast((last) => ({ trace: [...(last.trace || []), step] }));
      const attachSources = (sources) => patchLast(() => ({ sources }));

      try {
        await streamChat(history, {
          onDelta: appendToAssistant,
          onUsage: attachUsage,
          onStatus: appendTrace,
          onSources: attachSources,
          signal: controller.signal,
          model,
          // "No memory" selected in the composer = plain chat for this message,
          // even with expert mode on.
          useMemory: expertEnabled && memory !== NO_MEMORY,
          domain,
          memory: memory === NO_MEMORY ? null : memory,
          retrieval,
          // Archive recall happens server-side, in-process — no extra round
          // trip. The wide flag marks explicitly past-referential phrasing.
          recall: memoryEnabled,
          recallWide: looksPastReferential(text),
        });

        if (isFirstExchange && answer) {
          onAutoTitle?.([userMsg, { role: "assistant", content: answer }]);
        }

        // Memory judge: only when enabled, and (when the pre-filter is on) only
        // if the user's message OR the reply looks fact-bearing — the reply
        // check catches terse facts like "lebanon" the user filter misses.
        if (
          memoryEnabled &&
          (!prefilterEnabled ||
            looksMemorable(text) ||
            replyLooksMemorable(answer))
        ) {
          const context = { domain, memory: memory === NO_MEMORY ? null : memory };
          onJudgeMemory?.([userMsg, { role: "assistant", content: answer }], context).then(
            (result) => {
              if (!result) return;
              const quote = (fs) => fs.map((f) => `“${f}”`).join(", ");
              const parts = [];
              if (result.profileUpdated?.length) parts.push(`Profile updated: ${result.profileUpdated.join(", ")}`);
              if (result.added?.length) parts.push(`Remembered ${quote(result.added)}`);
              if (result.updated?.length) parts.push(`Updated to ${quote(result.updated)}`);
              if (result.removed?.length) parts.push(`Forgot ${quote(result.removed)}`);
              if (result.retired?.length) parts.push(`Archived ${quote(result.retired)}`);
              if (result.beliefsAdded?.length) parts.push(`Noted your view: ${quote(result.beliefsAdded)}`);
              if (result.beliefsUpdated?.length) parts.push(`Updated your view: ${quote(result.beliefsUpdated)}`);
              if (result.consolidated) parts.push("Memory consolidated");
              if (parts.length) onMemoryNote?.(parts.join(" · "));
            },
          );
        }
      } catch (err) {
        if (err.name !== "AbortError") setError(err.message);
      } finally {
        setIsStreaming(false);
        abortRef.current = null;
      }
    },
    [
      messages,
      setMessages,
      character,
      memoryContext,
      memoryReady,
      documents,
      memoryEnabled,
      prefilterEnabled,
      expertEnabled,
      memory,
      retrieval,
      domain,
      model,
      onUsage,
      onAutoTitle,
      onJudgeMemory,
      onMemoryNote,
    ],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  return { isStreaming, error, sendMessage, stop };
}

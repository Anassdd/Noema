import { useCallback, useRef, useState } from "react";

import { NO_MEMORY, streamChat } from "../api/chat.js";
import { buildSystemMessage } from "../lib/systemPrompt.js";
import { looksMemorable, replyLooksMemorable } from "../lib/memoryFilter.js";

// Runs one chat turn: builds the request (system prompt + real turns), streams
// the answer into the in-flight assistant message, then fires the
// fire-and-forget extras — auto-title on the first exchange, and the LLM memory
// judge when warranted. Owns the streaming/error/abort state.
export function useChatStream({
  messages,
  setMessages,
  character,
  memories,
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
}) {
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState(null);
  const abortRef = useRef(null);

  const sendMessage = useCallback(
    async (text) => {
      const userMsg = { role: "user", content: text };
      const isFirstExchange = messages.length === 0;
      const shown = [...messages, userMsg]; // displayed transcript (may have notes)

      setMessages([...shown, { role: "assistant", content: "" }]);
      setError(null);
      setIsStreaming(true);

      // What the model sees: real turns only (notes/help stripped), with the
      // persona + documents + remembered facts pinned in front. When memory is
      // off, the saved facts are withheld from the prompt.
      const sys = buildSystemMessage(
        character,
        memoryEnabled ? memories : [],
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
              if (result.added?.length) parts.push(`Remembered ${quote(result.added)}`);
              if (result.updated?.length) parts.push(`Updated to ${quote(result.updated)}`);
              if (result.removed?.length) parts.push(`Forgot ${quote(result.removed)}`);
              if (result.beliefsAdded?.length) parts.push(`Noted your view: ${quote(result.beliefsAdded)}`);
              if (result.consolidated) parts.push("Memory consolidated");
              if (parts.length) {
                setMessages((prev) => [
                  ...prev,
                  { role: "note", content: parts.join(" · ") },
                ]);
              }
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
      memories,
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
    ],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  return { isStreaming, error, sendMessage, stop };
}
